"""Code that runs on every model response, in every configuration, before it is
shown or scored. Failures are logged, never silently retried.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

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


def postprocess(raw: str, known_evidence_ids: set[str]) -> PostprocessResult:
    """Parse, validate, drop citations to unknown records, mask numbers, flag wording.

    known_evidence_ids must already be scoped to the current business, so a
    citation to another business's record is dropped exactly like a made-up one.
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

    for key in _TEXT_FIELDS:
        if isinstance(data.get(key), str):
            masked = mask_numbers(data[key])
            if masked != data[key]:
                issues.append(f"masked_number_in_{key}")
            data[key] = masked

    cites = data.get("evidence")
    if isinstance(cites, list):
        kept = [c for c in cites if isinstance(c, dict) and c.get("evidence_id") in known_evidence_ids]
        for c in cites:
            if c not in kept:
                issues.append(f"dropped_unknown_evidence: {c.get('evidence_id') if isinstance(c, dict) else c}")
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
