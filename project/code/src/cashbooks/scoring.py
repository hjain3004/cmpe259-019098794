"""Deterministic scoring of responses against gold, run logs, and the course CSV.

No LLM judge: money is checked to the cent with its currency, dates in any common
written form, answer type against the expected label, and citations at document
level so C1's page chunks and C3's field spans are compared fairly.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.contracts.response import AssistantResponse

_MONEY = re.compile(r"^(-?\d+(?:\.\d{1,2})?)\s+([A-Z]{3})$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INV_ID = re.compile(r"\b[A-Za-z]{1,6}-\d+\b")


def _is_identifier(phrase: str) -> bool:
    """Identifiers (invoice numbers, emails, account digits) stay strictly matched."""
    return bool("@" in phrase or _INV_ID.search(phrase) or re.search(r"\d{4,}", phrase))


def _check_must_not(text_lower: str, must_not: list[str]) -> tuple[list[str], list[str]]:
    """Return (hits, skipped) for must_not phrases, ignoring negated/quoted wording phrases."""
    from cashbooks.safety import _is_negated_or_quoted

    hits: list[str] = []
    skipped: list[str] = []
    for p in must_not:
        low = p.lower()
        if not low:
            continue
        if _is_identifier(p):
            if low in text_lower:
                hits.append(p)
            continue
        found = False
        unnegated = False
        pos = 0
        while True:
            idx = text_lower.find(low, pos)
            if idx == -1:
                break
            found = True
            if not _is_negated_or_quoted(text_lower, idx, idx + len(low)):
                unnegated = True
                break
            pos = idx + len(low)
        if unnegated:
            hits.append(p)
        elif found:
            skipped.append(p)
    return hits, skipped


def money_variants(amount: Decimal) -> set[str]:
    a = abs(amount)
    plain, comma = f"{a:.2f}", f"{a:,.2f}"
    out = {plain, comma, f"${plain}", f"${comma}"}
    if a == a.to_integral_value():
        whole, whole_c = f"{int(a)}", f"{int(a):,}"
        out |= {f"${whole}", f"${whole_c}"}
    return out


def date_variants(d: date) -> set[str]:
    return {
        d.isoformat(), d.strftime("%m/%d/%Y"), f"{d.month}/{d.day}/{d.year}", f"{d.month}/{d.day}",
        d.strftime("%b %d, %Y"), d.strftime("%B %d, %Y"), f"{d.strftime('%b')} {d.day}, {d.year}",
        f"{d.strftime('%B')} {d.day}, {d.year}", f"{d.strftime('%b')} {d.day}", f"{d.strftime('%B')} {d.day}",
        f"{d.day} {d.strftime('%b')} {d.year}", f"{d.day} {d.strftime('%B')} {d.year}",
    }


def _text(resp: AssistantResponse) -> str:
    parts = [resp.answer, resp.clarifying_question or "", resp.next_step or ""]
    parts += resp.risk_indicators
    if resp.calculation:
        parts += resp.calculation.steps
    return " ".join(parts)


_UNPAID_RE = re.compile(
    r"\b(?:unpaid|not\s+paid|not\s+been\s+paid|has\s+not\s+been\s+paid|hasn't\s+been\s+paid|open|outstanding)\b",
    re.I,
)
_PARTIAL_RE = re.compile(
    r"\b(?:partially\s+paid|partly\s+paid|partial(?:\s+payment)?)\b",
    re.I,
)
_PAID_NEG_PREFIX = re.compile(
    r"(?:\b(?:not|never|un|partially|partly|haven't|hasn't|wasn't|isn't)\s+(?:been\s+|yet\s+|already\s+)?)$",
    re.I,
)
_PAID_WORD_RE = re.compile(r"\b(?:paid\s+in\s+full|paid|settled)\b", re.I)


def _match_paid(text: str) -> bool:
    for m in _PAID_WORD_RE.finditer(text):
        prefix = text[max(0, m.start() - 35) : m.start()]
        if not _PAID_NEG_PREFIX.search(prefix):
            return True
    return False


def check_value(expected: str, resp: AssistantResponse) -> bool:
    text = _text(resp)
    m = _MONEY.match(expected.strip())
    if m:
        try:
            amount = Decimal(m.group(1))
        except InvalidOperation:
            return False
        calc = resp.calculation.result if resp.calculation else None
        if calc and calc.amount == amount and calc.currency == m.group(2):
            return True
        return any(v in text for v in money_variants(amount))
    if _DATE.match(expected.strip()):
        d = date.fromisoformat(expected.strip())
        return any(v.lower() in text.lower() for v in date_variants(d))
    exp = expected.strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", exp):  # a bare number must stand alone, not inside a longer number
        return re.search(rf"(?<![\d.]){re.escape(exp)}(?![\d])", text) is not None
    if exp in ("yes", "no"):
        return re.search(rf"\b{exp}\b", text.lower()) is not None
    if exp in ("unpaid", "open"):
        return _UNPAID_RE.search(text) is not None
    if exp in ("partially paid", "partly paid", "partial"):
        return _PARTIAL_RE.search(text) is not None
    if exp == "paid":
        return _match_paid(text)
    return exp in text.lower()


def doc_level(evidence_id: str) -> str:
    """span_inv_NS-1048_total -> inv_NS-1048; span_msg_m03 -> msg_m03; txn_0193 -> txn_0193."""
    parts = evidence_id.split("_")
    if parts[0] == "span" and len(parts) >= 3:
        return f"{parts[1]}_{parts[2]}"
    return evidence_id


@dataclass
class TurnScore:
    parsed: bool
    answerability_ok: bool
    values: dict[str, bool] = field(default_factory=dict)
    evidence_recall: float | None = None
    evidence_precision: float | None = None
    must_not_hits: list[str] = field(default_factory=list)
    must_not_skipped: list[str] = field(default_factory=list)
    success: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def score_turn(resp: AssistantResponse | None, expected: Answerability, gold_values: dict, gold_evidence: list[str],
               must_not: list[str]) -> TurnScore:
    if resp is None:
        return TurnScore(parsed=False, answerability_ok=False, success=False)
    ans_ok = resp.answerability == expected
    values = {k: check_value(str(v), resp) for k, v in (gold_values or {}).items()}
    cited = {doc_level(c.evidence_id) for c in resp.evidence}
    gold = set(gold_evidence or [])
    recall = len(cited & gold) / len(gold) if gold else None
    precision = (len(cited & gold) / len(cited) if cited else 0.0) if gold else None
    text = _text(resp).lower()
    hits, skipped = _check_must_not(text, must_not)
    success = ans_ok and all(values.values()) and not hits and (recall is None or recall > 0)
    return TurnScore(True, ans_ok, values, recall, precision, hits, skipped, success)


# ---------------------------------------------------------------- logs


def write_log(rows: Iterable[LogRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(r.model_dump_json() + "\n")


def read_log(path: Path) -> list[LogRow]:
    with open(path, encoding="utf-8") as f:
        return [LogRow.model_validate_json(line) for line in f if line.strip()]


def export_course_csv(rows: list[LogRow], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["configuration", "query_id", "turn", "query", "expected_behavior",
                                          "response", "success", "notes"])
        w.writeheader()
        for r in rows:
            proj = r.course_projection()
            w.writerow({"configuration": r.configuration, "query_id": r.query_id, "turn": r.turn_index, **proj})


_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


def _extract_reply_stats(raw_response: str) -> tuple[int, int, str | None] | None:
    """Return (citation_count, answer_word_count, answerability) from a raw JSON reply, or None."""
    if not raw_response:
        return None
    raw = raw_response.strip()
    m = _FENCE.fullmatch(raw)
    if m:
        raw = m.group(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    cites = data.get("evidence")
    cite_count = len(cites) if isinstance(cites, list) else 0
    answer = data.get("answer")
    word_count = len(str(answer).split()) if isinstance(answer, str) else 0
    ans_type = data.get("answerability") if isinstance(data.get("answerability"), str) else None
    return cite_count, word_count, ans_type


def summarize(rows: list[LogRow]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        s = out.setdefault(r.configuration, {
            "turns": 0, "parsed": 0, "successes": 0, "answer_type_ok": 0,
            "values_ok": 0, "values_total": 0, "latency_ms": [], "tokens": [],
            "recalls": [], "precisions": [], "citations": [], "words": [],
            "unwarranted_warnings": 0, "unwarranted_warning_eligible": 0,
            "over_abstentions": 0, "over_abstention_eligible": 0,
        })
        s["turns"] += 1
        s["parsed"] += int(r.parsed_ok)
        s["successes"] += int(bool(r.success))
        s["answer_type_ok"] += int(bool(r.scores.get("answerability_ok")))
        vals = r.scores.get("values") or {}
        s["values_ok"] += sum(1 for v in vals.values() if v)
        s["values_total"] += len(vals)
        if r.scores.get("evidence_recall") is not None:
            s["recalls"].append(float(r.scores["evidence_recall"]))
        if r.scores.get("evidence_precision") is not None:
            s["precisions"].append(float(r.scores["evidence_precision"]))
        ans_type = None
        if r.parsed_ok:
            stats = _extract_reply_stats(r.raw_response)
            if stats is not None:
                s["citations"].append(stats[0])
                s["words"].append(stats[1])
                ans_type = stats[2]
        if r.expected in (Answerability.ANSWER, Answerability.CLARIFY):
            s["unwarranted_warning_eligible"] += 1
            if ans_type == Answerability.WARN.value:
                s["unwarranted_warnings"] += 1
        if r.expected == Answerability.ANSWER:
            s["over_abstention_eligible"] += 1
            if ans_type == Answerability.ABSTAIN.value:
                s["over_abstentions"] += 1
        s["latency_ms"].append(r.latency_ms)
        s["tokens"].append(r.input_tokens + r.output_tokens)
    for s in out.values():
        n = s["turns"] or 1
        lat = sorted(s.pop("latency_ms"))
        tok = s.pop("tokens")
        rec = s.pop("recalls")
        prec = s.pop("precisions")
        cites = s.pop("citations")
        words = sorted(s.pop("words"))
        s["success_rate"] = round(s["successes"] / n, 3)
        s["answer_type_accuracy"] = round(s["answer_type_ok"] / n, 3)
        s["value_accuracy"] = round(s["values_ok"] / s["values_total"], 3) if s["values_total"] else None
        s["unwarranted_warning_rate"] = (
            round(s["unwarranted_warnings"] / s["unwarranted_warning_eligible"], 3)
            if s["unwarranted_warning_eligible"] else None
        )
        s["over_abstention_rate"] = (
            round(s["over_abstentions"] / s["over_abstention_eligible"], 3)
            if s["over_abstention_eligible"] else None
        )
        s["mean_evidence_recall"] = round(sum(rec) / len(rec), 3) if rec else None
        s["mean_evidence_precision"] = round(sum(prec) / len(prec), 3) if prec else None
        s["mean_citations"] = round(sum(cites) / len(cites), 2) if cites else None
        s["median_words"] = words[len(words) // 2] if words else None
        s["p90_words"] = words[max(0, math.ceil(0.9 * len(words)) - 1)] if words else None
        s["under_120_words_share"] = round(sum(1 for w in words if w < 120) / len(words), 3) if words else None
        s["median_latency_s"] = round(lat[len(lat) // 2] / 1000, 2) if lat else None
        s["mean_tokens"] = round(sum(tok) / len(tok)) if tok else None
    return out


def conversation_success(rows: list[LogRow]) -> dict[str, dict[str, bool]]:
    """A conversation succeeds only when every scored turn succeeds."""
    out: dict[str, dict[str, bool]] = {}
    for r in rows:
        c = out.setdefault(r.configuration, {})
        c[r.query_id] = c.get(r.query_id, True) and bool(r.success)
    return out


def dump_json(obj, path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


_LABELS = ["lookup", "aggregation", "temporal", "linking", "comparison", "dialogue", "abstention"]


def _load_query_labels() -> dict[str, list[str]]:
    qpath = Path(__file__).resolve().parents[3] / "evaluation" / "queries.yaml"
    if not qpath.exists():
        return {}
    import yaml

    data = yaml.safe_load(qpath.read_text(encoding="utf-8")) or {}
    return {c["id"]: list(c.get("labels", [])) for c in data.get("conversations", []) if "id" in c}


def summarize_by_label(rows: list[LogRow], query_labels: dict[str, list[str]]) -> dict[str, dict[str, dict[str, int]]]:
    """Per-label, per-config turn counts: {label: {config: {'correct': int, 'total': int}}}."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    configs = list(dict.fromkeys(r.configuration for r in rows))
    for lbl in _LABELS:
        out[lbl] = {c: {"correct": 0, "total": 0} for c in configs}
    for r in rows:
        for lbl in query_labels.get(r.query_id, []):
            if lbl not in out:
                out[lbl] = {c: {"correct": 0, "total": 0} for c in configs}
            cell = out[lbl][r.configuration]
            cell["total"] += 1
            cell["correct"] += int(bool(r.success))
    return out


def write_run_outputs(rows: list[LogRow], out: Path, run_id: str, model: str, commit: str, bundle: str,
                      conv_ids: list[str], scored_turns: int, prompt_version: str,
                      query_labels: dict[str, list[str]] | None = None) -> list[str]:
    """course.csv, summary.json and summary.md for one run; returns the summary.md lines."""
    export_course_csv(rows, out / "course.csv")
    summary = summarize(rows)
    conv = conversation_success(rows)
    for cname, per in conv.items():
        summary[cname]["conversations"] = len(per)
        summary[cname]["conversation_successes"] = sum(per.values())
    qlabels = query_labels if query_labels is not None else _load_query_labels()
    by_label = summarize_by_label(rows, qlabels) if qlabels else {}
    dump_json({"run": run_id, "model": model, "commit": commit, "bundle": bundle,
               "configs": summary, "by_label": by_label, "per_conversation": conv}, out / "summary.json")
    lines = [f"# Run {run_id}", "", f"Model `{model}`, prompt `{prompt_version}`, commit `{commit}`, "
             f"scenario `{Path(bundle).name}`, {len(conv_ids)} conversations, {scored_turns} scored turns.", "",
             "| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for cname, s in summary.items():
        va = s["value_accuracy"]
        lines.append(f"| {cname} | {s['successes']}/{s['turns']} ({s['success_rate']:.0%}) | "
                     f"{s['conversation_successes']}/{s['conversations']} | {s['answer_type_accuracy']:.0%} | "
                     f"{'n/a' if va is None else format(va, '.0%')} | {s['parsed']}/{s['turns']} | "
                     f"{s['median_latency_s']} | {s['mean_tokens']} |")
    lines += [
        "",
        "## Error rates",
        "",
        "| Config | Unwarranted-warning rate | Over-abstention rate |",
        "| --- | --- | --- |",
    ]
    for cname, s in summary.items():
        uwr = s["unwarranted_warning_rate"]
        oar = s["over_abstention_rate"]
        uw_str = "n/a" if uwr is None else f"{s['unwarranted_warnings']}/{s['unwarranted_warning_eligible']} ({uwr:.0%})"
        oa_str = "n/a" if oar is None else f"{s['over_abstentions']}/{s['over_abstention_eligible']} ({oar:.0%})"
        lines.append(f"| {cname} | {uw_str} | {oa_str} |")
    lines += [
        "",
        "## Grounding and usability",
        "",
        "| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cname, s in summary.items():
        mr = s["mean_evidence_recall"]
        mp = s["mean_evidence_precision"]
        mc = s["mean_citations"]
        mw = s["median_words"]
        pw = s["p90_words"]
        u120 = s["under_120_words_share"]
        lines.append(
            f"| {cname} | {'n/a' if mr is None else f'{mr:.3f}'} | {'n/a' if mp is None else f'{mp:.3f}'} | "
            f"{'n/a' if mc is None else f'{mc:.2f}'} | {'n/a' if mw is None else mw} | "
            f"{'n/a' if pw is None else pw} | {'n/a' if u120 is None else f'{u120:.0%}'} |"
        )
    if by_label:
        cfg_names = list(summary.keys())
        lines += [
            "",
            "## Per-question-type turn success",
            "",
            "| Label | " + " | ".join(cfg_names) + " |",
            "| --- |" + " --- |" * len(cfg_names),
        ]
        for lbl, per_cfg in by_label.items():
            cells = [f"{per_cfg[c]['correct']}/{per_cfg[c]['total']}" if c in per_cfg else "0/0" for c in cfg_names]
            lines.append(f"| {lbl} | " + " | ".join(cells) + " |")
    lines += ["", "## Conversation success", "", "| Conversation | " + " | ".join(conv) + " |",
              "| --- |" + " --- |" * len(conv)]
    for q in conv_ids:
        lines.append(f"| {q} | " + " | ".join("pass" if conv[c].get(q) else "fail" for c in conv) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    return lines
