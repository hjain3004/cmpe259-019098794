"""Deterministic scoring of responses against gold, run logs, and the course CSV.

No LLM judge: money is checked to the cent with its currency, dates in any common
written form, answer type against the expected label, and citations at document
level so C1's page chunks and C3's field spans are compared fairly.
"""

from __future__ import annotations

import csv
import json
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
    hits = [p for p in must_not if p.lower() in text]
    success = ans_ok and all(values.values()) and not hits and (recall is None or recall > 0)
    return TurnScore(True, ans_ok, values, recall, precision, hits, success)


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


def summarize(rows: list[LogRow]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        s = out.setdefault(r.configuration, {"turns": 0, "parsed": 0, "successes": 0, "answer_type_ok": 0,
                                             "values_ok": 0, "values_total": 0, "latency_ms": [], "tokens": []})
        s["turns"] += 1
        s["parsed"] += int(r.parsed_ok)
        s["successes"] += int(bool(r.success))
        s["answer_type_ok"] += int(bool(r.scores.get("answerability_ok")))
        vals = r.scores.get("values") or {}
        s["values_ok"] += sum(1 for v in vals.values() if v)
        s["values_total"] += len(vals)
        s["latency_ms"].append(r.latency_ms)
        s["tokens"].append(r.input_tokens + r.output_tokens)
    for s in out.values():
        n = s["turns"] or 1
        lat = sorted(s.pop("latency_ms"))
        tok = s.pop("tokens")
        s["success_rate"] = round(s["successes"] / n, 3)
        s["answer_type_accuracy"] = round(s["answer_type_ok"] / n, 3)
        s["value_accuracy"] = round(s["values_ok"] / s["values_total"], 3) if s["values_total"] else None
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


def write_run_outputs(rows: list[LogRow], out: Path, run_id: str, model: str, commit: str, bundle: str,
                      conv_ids: list[str], scored_turns: int, prompt_version: str) -> list[str]:
    """course.csv, summary.json and summary.md for one run; returns the summary.md lines."""
    export_course_csv(rows, out / "course.csv")
    summary = summarize(rows)
    conv = conversation_success(rows)
    for cname, per in conv.items():
        summary[cname]["conversations"] = len(per)
        summary[cname]["conversation_successes"] = sum(per.values())
    dump_json({"run": run_id, "model": model, "commit": commit, "bundle": bundle,
               "configs": summary, "per_conversation": conv}, out / "summary.json")
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
    lines += ["", "## Conversation success", "", "| Conversation | " + " | ".join(conv) + " |",
              "| --- |" + " --- |" * len(conv)]
    for q in conv_ids:
        lines.append(f"| {q} | " + " | ".join("pass" if conv[c].get(q) else "fail" for c in conv) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    return lines
