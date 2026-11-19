"""Attribute causes for failing challenge turns and write <run_folder>/analysis.md.

    cd project
    ../.venv/bin/python evaluation/challenge/analyze.py evaluation/results/challenge/<run> [--human human_scores.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cashbooks.configs.answer import MAX_TOOL_CALLS
from cashbooks.scoring import date_variants, money_variants
from review_sheet import (
    extract_tool_calls,
    format_reply_text,
    is_deterministic_pass,
    is_rubric_turn,
    load_challenge_metadata,
    load_log_rows,
    load_summary,
    resolve_turn_gold,
)

CAUSES = (
    "test_design",
    "extraction",
    "dialogue_state",
    "tool_budget",
    "orchestration",
    "tool_coverage",
    "generation",
    "needs human tagging",
)

_MONEY_RE = re.compile(r"^(-?\d+(?:\.\d{1,2})?)\s+([A-Z]{3})$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INV_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z]{2,6}-\d{2,6})(?![A-Za-z0-9_])")
_FOLLOWUP_RE = re.compile(
    r"\b(?:it|its|that|those|them|both|first|second|third|last|before\s+that|previous|same)\b",
    re.I,
)
_PAID_QUERY_RE = re.compile(r"\b(?:paid|settled|closed|already\s+pay)\b", re.I)
_BANK_QUERY_RE = re.compile(r"\b(?:bank|account|routing|remit|payment\s+details|changed)\b", re.I)
_TOTAL_DUE_RE = re.compile(r"\b(?:total\s+(?:owed|due)|how\s+much\s+(?:do\s+we\s+)?owe|amount\s+due)\b", re.I)
_PURCHASES_RE = re.compile(r"\b(?:how\s+many|quantity|quantities|spend|spent|purchased|purchases|bought)\b", re.I)
_MATCH_PAY_RE = re.compile(r"\b(?:debit|transaction|match(?:ed)?|duplicate|twice|double[-\s]paid)\b", re.I)


def value_in_text(expected: Any, text: str) -> bool:
    """Return True if an expected value (money, date, status, number, or string) matches `text`."""
    if expected is None:
        return True
    s = str(expected).strip()
    if not s or not text:
        return False
    m = _MONEY_RE.match(s)
    if m:
        try:
            amt = Decimal(m.group(1))
        except InvalidOperation:
            return False
        return any(v in text for v in money_variants(amt))
    if _DATE_RE.match(s):
        try:
            d = date.fromisoformat(s)
            return any(v.lower() in text.lower() for v in date_variants(d))
        except ValueError:
            return s.lower() in text.lower()
    low = s.lower()
    if re.fullmatch(r"\d+(?:\.\d+)?", low):
        return re.search(rf"(?<![\d.]){re.escape(low)}(?![\d])", text) is not None
    if low in ("yes", "no"):
        return re.search(rf"\b{low}\b", text.lower()) is not None
    return low in text.lower()


def load_human_scores(csv_path: Path | None) -> dict[tuple[str, int, str], dict[str, Any]]:
    """Load human_scores.csv keyed by (query_id, turn_index, configuration)."""
    out: dict[tuple[str, int, str], dict[str, Any]] = {}
    if not csv_path or not csv_path.exists():
        return out
    with open(csv_path, encoding="utf-8", newline="") as f:
        for rec in csv.DictReader(f):
            qid = str(rec.get("query_id") or "").strip()
            if not qid:
                continue
            try:
                ti = int(str(rec.get("turn_index") or "0").strip())
            except ValueError:
                continue
            cfg = str(rec.get("configuration") or "").strip()
            raw_score = str(rec.get("rubric_score") or "").strip()
            score = int(raw_score) if raw_score in ("0", "1", "2") else None
            notes = str(rec.get("notes") or "")
            out[(qid, ti, cfg)] = {"rubric_score": score, "notes": notes}
    return out


def _get_human(
    human_map: dict[tuple[str, int, str], dict[str, Any]],
    qid: str,
    ti: int,
    cfg: str,
) -> dict[str, Any] | None:
    return human_map.get((qid, ti, cfg)) or human_map.get((qid, ti, ""))


def _load_ledger(run_folder: Path, ledger_path: Path | None, bundle_dir: Path | None) -> dict[str, Any]:
    candidates = [ledger_path, run_folder / "ledger.json", bundle_dir / "ledger.json" if bundle_dir else None]
    for cand in candidates:
        if cand and cand.exists():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return {}


def _index_ledger(ledger: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    invoices = {
        str(inv["invoice_number"]): inv
        for inv in ledger.get("invoices", [])
        if isinstance(inv, dict) and inv.get("invoice_number")
    }
    vendors = {
        str(v["vendor_id"]): v
        for v in ledger.get("vendors", [])
        if isinstance(v, dict) and v.get("vendor_id")
    }
    return invoices, vendors


def _decimal_equal(a: Any, b: Any) -> bool:
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(a).strip() == str(b).strip()


def _money_field_mismatch(tool_val: Any, ledger_amount: Any, ledger_currency: str | None) -> str | None:
    if tool_val is None or ledger_amount is None:
        return None
    if isinstance(tool_val, dict):
        amt = tool_val.get("amount")
        curr = tool_val.get("currency")
        if amt is not None and not _decimal_equal(amt, ledger_amount):
            return f"{amt} vs {ledger_amount}"
        if curr and ledger_currency and str(curr).upper() != ledger_currency.upper():
            return f"{curr} vs {ledger_currency}"
    elif not _decimal_equal(tool_val, ledger_amount):
        return f"{tool_val} vs {ledger_amount}"
    return None


def check_extraction_mismatch(
    tool_calls: list[dict[str, Any]],
    invoices: dict[str, dict[str, Any]],
) -> str | None:
    """Compare parsed JSON tool outputs against ledger.json; return mismatch reason if wrong."""
    if not invoices:
        return None
    for tc in tool_calls:
        raw_res = tc.get("result")
        if isinstance(raw_res, str):
            try:
                parsed = json.loads(raw_res)
            except json.JSONDecodeError:
                continue
        elif isinstance(raw_res, dict):
            parsed = raw_res
        else:
            continue
        if not isinstance(parsed, dict):
            continue

        records: list[dict[str, Any]] = []
        if isinstance(parsed.get("bill"), dict):
            b = dict(parsed["bill"])
            for extra in ("subtotal", "tax"):
                if parsed.get(extra) is not None and b.get(extra) is None:
                    b[extra] = parsed[extra]
            records.append(b)
        for item in parsed.get("bills") or []:
            if isinstance(item, dict):
                records.append(item)
        if parsed.get("invoice_number"):
            records.append(parsed)

        tname = tc.get("name") or "tool"
        for rec in records:
            inv_num = str(rec.get("invoice_number") or "")
            if inv_num not in invoices:
                continue
            truth = invoices[inv_num]
            t_curr = truth.get("currency")
            for field in ("total", "subtotal", "tax"):
                if rec.get(field) is not None and truth.get(field) is not None:
                    diff = _money_field_mismatch(rec[field], truth[field], t_curr)
                    if diff:
                        return f"{tname} returned {inv_num}.{field}={diff} vs ledger"
            for df in ("issue_date", "stated_due_date"):
                if rec.get(df) and truth.get(df) and str(rec[df]) != str(truth[df]):
                    return f"{tname} returned {inv_num}.{df}={rec[df]} vs ledger {truth[df]}"
            on_doc = rec.get("on_document")
            remit = truth.get("remit") or {}
            if isinstance(on_doc, dict) and on_doc.get("account_last4") and remit.get("account_number"):
                exp_last4 = str(remit["account_number"])[-4:]
                if str(on_doc["account_last4"]) != exp_last4:
                    return f"{tname} returned {inv_num} account_last4={on_doc['account_last4']} vs ledger {exp_last4}"
    return None


def _check_dialogue_state_regression(
    row: dict[str, Any],
    prior_rows: list[dict[str, Any]],
    gold_info: dict[str, Any],
    meta: dict[tuple[str, int], dict[str, Any]],
    reply_blob: str,
    tool_calls: list[dict[str, Any]],
) -> str | None:
    """Detect whether a value or entity established in an earlier turn disappeared or changed."""
    ti = int(row.get("turn_index", 0))
    if ti == 0 or not prior_rows:
        return None

    req_values = gold_info.get("required_values") or {}
    scores = row.get("scores") or {}
    val_results = scores.get("values") if isinstance(scores.get("values"), dict) else {}
    turn_text = str(row.get("turn_text") or "")

    prior_reply_text = "\n".join(
        format_reply_text(str(p.get("raw_response") or "")) + "\n" + str(p.get("raw_response") or "")
        for p in prior_rows
    )
    prior_gold_values: dict[str, Any] = {}
    for p in prior_rows:
        pg = resolve_turn_gold(p, meta)
        for k, v in (pg.get("required_values") or {}).items():
            prior_gold_values[k] = v

    # Case 1: Current turn requires a value that appeared in an earlier turn's reply or gold,
    # yet is now missing from the current reply.
    for k, expected in req_values.items():
        if val_results.get(k) is False or not value_in_text(expected, reply_blob):
            if value_in_text(expected, prior_reply_text) or (
                k in prior_gold_values and str(prior_gold_values[k]) == str(expected)
            ):
                return f"earlier turn had {k}={expected!r}, missing or altered in turn {ti}"

    # Case 2: Follow-up turn uses anaphora without switching entity, yet omits/replaces
    # an invoice number established in an earlier turn.
    if _FOLLOWUP_RE.search(turn_text) and not _INV_RE.findall(turn_text):
        prior_invs = list(dict.fromkeys(_INV_RE.findall(prior_reply_text)))
        if len(prior_invs) == 1:
            expected_inv = prior_invs[0]
            curr_invs = list(dict.fromkeys(_INV_RE.findall(reply_blob)))
            tool_blob = json.dumps(tool_calls, ensure_ascii=False)
            if curr_invs and expected_inv not in curr_invs:
                return f"follow-up shifted earlier invoice {expected_inv} to {', '.join(curr_invs)}"
            if not curr_invs and expected_inv not in reply_blob and expected_inv not in tool_blob:
                return f"follow-up dropped earlier invoice {expected_inv}"

    # Case 3: Earlier gold value for an overlapping key changed in this reply when key repeated.
    for k, prev_val in prior_gold_values.items():
        if k in req_values and str(req_values[k]) == str(prev_val):
            if not value_in_text(prev_val, reply_blob):
                return f"value for {k} from earlier turn ({prev_val}) missing or changed"

    return None


def _missing_orchestration_tool(
    row: dict[str, Any],
    gold_info: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    prior_rows: list[dict[str, Any]],
) -> str | None:
    """Return reason if a tool capable of supplying missing facts was not called."""
    called = {tc["name"] for tc in tool_calls}
    expected_tools = gold_info.get("expected_tools") or []
    for t in expected_tools:
        if t not in called:
            return f"expected tool {t} was not called"

    ctx = row.get("context") or []
    is_retrieval_cfg = any(isinstance(c, dict) and "chunk_id" in c for c in ctx)
    if not tool_calls and not is_retrieval_cfg:
        return "no tools were called for a data-dependent turn"

    turn_text = str(row.get("turn_text") or "")
    all_text = " ".join([turn_text] + [str(p.get("turn_text") or "") for p in prior_rows])

    if _PAID_QUERY_RE.search(turn_text) and "get_bill_status" not in called:
        used_open_without_settled = any(
            tc["name"] == "list_open_bills" and not (tc.get("args") or {}).get("include_settled")
            for tc in tool_calls
        )
        if used_open_without_settled:
            return "list_open_bills called without include_settled=True (and get_bill_status omitted)"

    if (_INV_RE.search(turn_text) or (prior_rows and _INV_RE.search(all_text) and _FOLLOWUP_RE.search(turn_text))) and (
        "get_bill_status" not in called
    ):
        return "invoice referenced without calling get_bill_status"

    if _BANK_QUERY_RE.search(turn_text) and "compare_vendor_payment_details" not in called:
        return "bank/remit query did not call compare_vendor_payment_details"

    if _TOTAL_DUE_RE.search(turn_text) and "sum_amount_due" not in called and "list_open_bills" not in called:
        return "total-due query did not call sum_amount_due or list_open_bills"

    if _PURCHASES_RE.search(turn_text) and "summarize_purchases" not in called:
        return "purchase/quantity query did not call summarize_purchases"

    if _MATCH_PAY_RE.search(turn_text) and "match_payments" not in called and "get_bill_status" not in called:
        return "payment-matching query did not call match_payments or get_bill_status"

    return None


def attribute_failure(
    row: dict[str, Any],
    prior_rows: list[dict[str, Any]],
    gold_info: dict[str, Any],
    meta: dict[tuple[str, int], dict[str, Any]],
    human_entry: dict[str, Any] | None,
    invoices: dict[str, dict[str, Any]],
    max_tool_calls: int,
) -> tuple[str, str]:
    """Assign one primary failure cause and evidence reason for a failing or 0-rubric turn."""
    human_notes = str((human_entry or {}).get("notes") or "").strip()
    if human_notes.upper().startswith("TEST:"):
        return "test_design", f"Human note flagged test design ({human_notes})"

    tool_calls = extract_tool_calls(row)
    ext_reason = check_extraction_mismatch(tool_calls, invoices)
    if ext_reason:
        return "extraction", ext_reason
    scores = row.get("scores") or {}
    if row.get("error_label") == "extraction" or scores.get("error_label") == "extraction":
        return "extraction", "Logged extraction error label"

    raw_resp = str(row.get("raw_response") or "")
    reply_blob = format_reply_text(raw_resp) + "\n" + raw_resp

    dlg_reason = _check_dialogue_state_regression(row, prior_rows, gold_info, meta, reply_blob, tool_calls)
    if dlg_reason:
        return "dialogue_state", dlg_reason

    req_values = gold_info.get("required_values") or {}
    tool_blob = "\n".join(
        str(tc.get("result") if not isinstance(tc.get("result"), (dict, list)) else json.dumps(tc["result"]))
        for tc in tool_calls
    )
    missing_in_tools = [k for k, v in req_values.items() if not value_in_text(v, tool_blob)]
    parsed_ok = bool(row.get("parsed_ok", scores.get("parsed", True)))
    notes_low = str(row.get("notes") or "").lower()
    det_pass = is_deterministic_pass(row)

    if len(tool_calls) >= max_tool_calls and (not parsed_ok or bool(missing_in_tools) or "tool" in notes_low):
        return "tool_budget", f"Reached max tool budget ({len(tool_calls)}/{max_tool_calls})"

    if det_pass is False and req_values:
        if not missing_in_tools:
            return "generation", "All required values were present in tool outputs, but reply failed"
        orch_reason = _missing_orchestration_tool(row, gold_info, tool_calls, prior_rows)
        if orch_reason:
            return "orchestration", orch_reason
        if tool_calls:
            return "tool_coverage", f"Tools ran, but no output contained: {', '.join(missing_in_tools)}"
        return "needs human tagging", "No tool calls and retrieval context insufficient to isolate cause"

    # Turns with no required scalar values (ABSTAIN / CLARIFY / WARN / rubric-only)
    ans_ok = scores.get("answerability_ok", True)
    must_not_hits = scores.get("must_not_hits") or []
    allowed_types = gold_info.get("allowed_types") or []

    if det_pass is False:
        if not parsed_ok or must_not_hits:
            return "generation", "Reply failed parsing or violated must_not rule"
        if ans_ok is False:
            if not tool_calls and "ABSTAIN" not in allowed_types:
                orch_reason = _missing_orchestration_tool(row, gold_info, tool_calls, prior_rows)
                if orch_reason:
                    return "orchestration", orch_reason
            return "generation", "Reply used the wrong answerability type"
        if scores.get("evidence_recall") == 0:
            if tool_calls:
                return "generation", "Tool outputs retrieved, but reply missed required evidence citations"
            orch_reason = _missing_orchestration_tool(row, gold_info, tool_calls, prior_rows)
            if orch_reason:
                return "orchestration", orch_reason

    rubric_score = (human_entry or {}).get("rubric_score")
    if det_pass is True and rubric_score == 0:
        return "needs human tagging", "Passed deterministic checks; scored 0 on open rubric without TEST: prefix"

    return "needs human tagging", "No deterministic attribution rule matched"


def analyze_run(
    run_folder: Path,
    human_csv: Path | None = None,
    gold_path: Path | None = None,
    queries_path: Path | None = None,
    ledger_path: Path | None = None,
    out_path: Path | None = None,
    max_tool_calls: int | None = None,
) -> Path:
    """Analyze a challenge run folder and write analysis.md."""
    rows = load_log_rows(run_folder)
    summary = load_summary(run_folder)
    meta, bundle_dir = load_challenge_metadata(run_folder, gold_path=gold_path, queries_path=queries_path)
    ledger = _load_ledger(run_folder, ledger_path, bundle_dir)
    invoices, _ = _index_ledger(ledger)
    human_map = load_human_scores(human_csv)
    budget = int(max_tool_calls or summary.get("max_tool_calls") or MAX_TOOL_CALLS)

    by_conv_cfg: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_conv_cfg[(str(r.get("configuration") or ""), str(r.get("query_id") or ""))].append(r)
    for k in by_conv_cfg:
        by_conv_cfg[k].sort(key=lambda x: int(x.get("turn_index", 0)))

    cause_counts: Counter[str] = Counter()
    conv_fail_causes: dict[str, Counter[str]] = defaultdict(Counter)
    cfg_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"turns": 0, "det_pass": 0, "rubric_turns": 0, "rubric_scored": 0, "rubric_ge1": 0, "combined_pass": 0}
    )
    conv_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"turns": 0, "det_pass": 0, "rubric_scored": 0, "rubric_ge1": 0, "combined_pass": 0, "failures": 0}
    )
    failure_details: list[dict[str, Any]] = []

    for row in rows:
        det_pass = is_deterministic_pass(row)
        if det_pass is None:
            continue  # Skip setup turns
        qid = str(row.get("query_id") or "")
        ti = int(row.get("turn_index", 0))
        cfg = str(row.get("configuration") or "")
        gold_info = resolve_turn_gold(row, meta)
        human_entry = _get_human(human_map, qid, ti, cfg)
        rubric_score = (human_entry or {}).get("rubric_score")
        rubric_flag = is_rubric_turn(row, gold_info) or (rubric_score is not None)

        cs = cfg_stats[cfg]
        qs = conv_stats[qid]
        cs["turns"] += 1
        qs["turns"] += 1
        if det_pass:
            cs["det_pass"] += 1
            qs["det_pass"] += 1
        if rubric_flag:
            cs["rubric_turns"] += 1
        if rubric_score is not None:
            cs["rubric_scored"] += 1
            qs["rubric_scored"] += 1
            if rubric_score >= 1:
                cs["rubric_ge1"] += 1
                qs["rubric_ge1"] += 1

        # Combined pass: deterministic pass AND rubric >= 1 (for turns without a rubric score,
        # require deterministic pass only when not a rubric turn or no human CSV was provided).
        if rubric_score is not None:
            comb_ok = bool(det_pass and rubric_score >= 1)
        elif rubric_flag and human_csv is not None:
            comb_ok = False
        else:
            comb_ok = bool(det_pass)

        if comb_ok:
            cs["combined_pass"] += 1
            qs["combined_pass"] += 1

        if (det_pass is False) or (rubric_score == 0):
            conv_history = [p for p in by_conv_cfg[(cfg, qid)] if int(p.get("turn_index", 0)) < ti]
            cause, reason = attribute_failure(
                row, conv_history, gold_info, meta, human_entry, invoices, budget
            )
            cause_counts[cause] += 1
            conv_fail_causes[qid][cause] += 1
            qs["failures"] += 1
            failure_details.append(
                {
                    "query_id": qid,
                    "turn_index": ti,
                    "configuration": cfg,
                    "det_pass": det_pass,
                    "rubric_score": rubric_score if rubric_score is not None else "—",
                    "cause": cause,
                    "reason": reason,
                }
            )

    # Render analysis.md
    lines: list[str] = [f"# Challenge Analysis: {run_folder.name}", ""]
    lines.append(f"- Scored turns: {sum(s['turns'] for s in cfg_stats.values())}")
    lines.append(f"- Failing or 0-rubric turns analyzed: {len(failure_details)}")
    lines.append(f"- Human scores: `{human_csv}`" if human_csv else "- Human scores: none provided")
    lines.append("")

    lines.extend(
        [
            "## Combined Pass Table (Deterministic Pass AND Rubric >= 1)",
            "",
            "| Config | Turns | Det Pass | Rubric Scored | Rubric >= 1 | Combined Pass |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for cfg in sorted(cfg_stats):
        s = cfg_stats[cfg]
        t = s["turns"]
        dp = s["det_pass"]
        rs = s["rubric_scored"]
        rg = s["rubric_ge1"]
        cp = s["combined_pass"]
        pct = f"{(100 * cp / t):.0f}%" if t else "0%"
        r_col = f"{rg}/{rs}" if rs else "0/0"
        lines.append(f"| {cfg or 'default'} | {t} | {dp}/{t} | {rs} | {r_col} | {cp}/{t} ({pct}) |")
    lines.append("")

    lines.extend(["## Counts per Cause", "", "| Cause | Count |", "| --- | --- |"])
    for cause in CAUSES:
        lines.append(f"| {cause} | {cause_counts[cause]} |")
    lines.append("")

    lines.extend(
        [
            "## Counts per Conversation",
            "",
            "| Conversation | Turns | Det Pass | Rubric >= 1 | Combined Pass | Failed / 0-Rubric | Causes |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for qid in sorted(conv_stats):
        s = conv_stats[qid]
        r_col = f"{s['rubric_ge1']}/{s['rubric_scored']}" if s["rubric_scored"] else "—"
        causes_str = ", ".join(f"{c}:{n}" for c, n in sorted(conv_fail_causes[qid].items())) or "—"
        lines.append(
            f"| {qid} | {s['turns']} | {s['det_pass']}/{s['turns']} | {r_col} | "
            f"{s['combined_pass']}/{s['turns']} | {s['failures']} | {causes_str} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Attributed Failures",
            "",
            "| Query | Turn | Config | Det Pass | Rubric | Cause | Evidence |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if failure_details:
        for fd in failure_details:
            lines.append(
                f"| {fd['query_id']} | {fd['turn_index']} | {fd['configuration'] or 'default'} | "
                f"{'PASS' if fd['det_pass'] else 'FAIL'} | {fd['rubric_score']} | "
                f"`{fd['cause']}` | {fd['reason']} |"
            )
    else:
        lines.append("| — | — | — | — | — | — | No failing or 0-rubric turns |")
    lines.append("")

    out = out_path or (run_folder / "analysis.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze challenge failures and human rubric scores.")
    ap.add_argument("run_folder", type=Path, help="Run directory containing log.jsonl")
    ap.add_argument("--human", type=Path, help="Optional human_scores.csv exported from review.html")
    ap.add_argument("--gold", type=Path, help="Optional gold YAML override")
    ap.add_argument("--queries", type=Path, help="Optional challenge queries YAML override")
    ap.add_argument("--ledger", type=Path, help="Optional ledger.json override")
    ap.add_argument("--out", type=Path, help="Output markdown path (default <run_folder>/analysis.md)")
    ap.add_argument("--max-tool-calls", type=int, help=f"Max tool call budget (default {MAX_TOOL_CALLS})")
    a = ap.parse_args()

    out = analyze_run(
        a.run_folder,
        human_csv=a.human,
        gold_path=a.gold,
        queries_path=a.queries,
        ledger_path=a.ledger,
        out_path=a.out,
        max_tool_calls=a.max_tool_calls,
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
