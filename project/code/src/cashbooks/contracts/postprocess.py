"""Code that runs on every model response, in every configuration, before it is
shown or scored. Failures are logged, never silently retried.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from pydantic import ValidationError

from .common import Answerability
from .response import AssistantResponse

# Unbroken runs of 6+ digits (account / routing numbers) are cut to their last
# four digits. Hyphenated runs are left alone so ISO dates and phone numbers on
# file survive; the generator prints account numbers without separators.
_DIGIT_RUN = re.compile(r"\b\d{6,}\b")

# Conclusions the assistant must never state. Flagged for the human rubric,
# because "verified" can appear legitimately ("the account you verified in May").
_BANNED = re.compile(r"\b(safe to pay|fraud(?:ulent)?|scam|verified|authenticated|legitimate)\b", re.I)

_TEXT_FIELDS = ("answer", "clarifying_question", "next_step")
_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


@dataclass
class PostprocessResult:
    response: AssistantResponse | None
    issues: list[str] = field(default_factory=list)
    wording_flags: list[str] = field(default_factory=list)


def mask_numbers(text: str) -> str:
    def _mask(m: re.Match) -> str:
        return f"****{m.group()[-4:]}"

    return _DIGIT_RUN.sub(_mask, text)


def postprocess(raw: str, known_evidence_ids: set[str], default_as_of: date | None = None) -> PostprocessResult:
    """Parse, validate, drop citations to unknown records, mask numbers, flag wording.

    known_evidence_ids must already be scoped to the current business, so a
    citation to another business's record is dropped exactly like a made-up one.
    Every schema normalization is logged in `issues`; `raw` itself is never altered.
    """
    issues: list[str] = []
    fenced = _FENCE.fullmatch(raw.strip())
    if fenced:  # a reply wrapped in one ```json fence; anything else must be bare JSON
        raw = fenced.group(1)
        issues.append("unwrapped_code_fence")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return PostprocessResult(None, [f"invalid_json: {e.msg}"])
    if not isinstance(data, dict):
        return PostprocessResult(None, ["invalid_json: top level is not an object"])

    calc_obj = data.get("calculation")
    if "result" in data and isinstance(calc_obj, dict) and calc_obj.get("result") is None:
        calc_obj["result"] = data.pop("result")
        issues.append("moved_result_into_calculation")

    allowed_keys = set(AssistantResponse.model_fields.keys())
    for key in [k for k in list(data.keys()) if k not in allowed_keys]:
        data.pop(key)
        issues.append(f"dropped_unknown_key: {key}")

    if data.get("as_of") in (None, "") and default_as_of is not None:
        data["as_of"] = default_as_of.isoformat()
        issues.append("filled_missing_as_of")

    for opt_key in ("clarifying_question", "next_step"):
        if isinstance(data.get(opt_key), str) and data[opt_key].strip() == "":
            data[opt_key] = None
            issues.append(f"normalized_empty_{opt_key}")

    if "risk_indicators" in data and data.get("risk_indicators") is None:
        data["risk_indicators"] = []
        issues.append("normalized_null_risk_indicators")

    if "evidence" in data and data.get("evidence") is None:
        data["evidence"] = []
        issues.append("normalized_null_evidence")

    ans_val = data.get("answerability")
    if ans_val == Answerability.ABSTAIN.value and data.get("calculation") is not None:
        data["calculation"] = None
        issues.append("dropped_abstain_calculation")
    elif ans_val == Answerability.CLARIFY.value and data.get("calculation") is not None:
        data["calculation"] = None
        issues.append("dropped_clarify_calculation")

    for key in _TEXT_FIELDS:
        if isinstance(data.get(key), str):
            masked = mask_numbers(data[key])
            if masked != data[key]:
                issues.append(f"masked_number_in_{key}")
            data[key] = masked

    if isinstance(data.get("risk_indicators"), list):
        masked_risks: list = []
        risk_changed = False
        for item in data["risk_indicators"]:
            if isinstance(item, str):
                m_item = mask_numbers(item)
                risk_changed = risk_changed or (m_item != item)
                masked_risks.append(m_item)
            else:
                masked_risks.append(item)
        if risk_changed:
            issues.append("masked_number_in_risk_indicators")
        data["risk_indicators"] = masked_risks

    calc = data.get("calculation")
    if isinstance(calc, dict) and isinstance(calc.get("steps"), list):
        masked_steps: list = []
        steps_changed = False
        for step in calc["steps"]:
            if isinstance(step, str):
                m_step = mask_numbers(step)
                steps_changed = steps_changed or (m_step != step)
                masked_steps.append(m_step)
            else:
                masked_steps.append(step)
        if steps_changed:
            issues.append("masked_number_in_calculation")
        calc["steps"] = masked_steps

    cites = data.get("evidence")
    if isinstance(cites, list):
        kept = [c for c in cites if isinstance(c, dict) and c.get("evidence_id") in known_evidence_ids]
        for c in cites:
            if c not in kept:
                issues.append(f"dropped_unknown_evidence: {c.get('evidence_id') if isinstance(c, dict) else c}")
        supp_changed = False
        for c in kept:
            if isinstance(c.get("supports"), str):
                m_supp = mask_numbers(c["supports"])
                if m_supp != c["supports"]:
                    supp_changed = True
                    c["supports"] = m_supp
        if supp_changed:
            issues.append("masked_number_in_evidence")
        data["evidence"] = kept

    try:
        resp = AssistantResponse.model_validate(data)
    except ValidationError as e:
        first = e.errors()[0]
        return PostprocessResult(None, issues + [f"contract_violation: {first['msg']}"])

    flags = [
        f"{key}: '{m.group()}'"
        for key in _TEXT_FIELDS
        for m in _BANNED.finditer(getattr(resp, key) or "")
    ]
    return PostprocessResult(resp, issues, flags)
