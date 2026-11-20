"""Run multi-turn challenge sets (CH1–CH7) by reusing run_eval.py and scoring.py.

    cd project
    python evaluation/run_challenge.py data/dev/cafe_01 --configs C3 --llm scripted
    python evaluation/run_challenge.py data/dev/cafe_01 --configs C3

Writes evaluation/results/challenge/<timestamp>-<bundle>/:
    log.jsonl   one LogRow per turn
    course.csv  query, expected_behavior, response, success, notes (+ config, query_id, turn)
    summary.md  deterministic pass rate per config and conversation, plus blank human rubric table
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from cashbooks.configs.answer import PROMPT_VERSION, Turn, build_configs, format_turn_assistant
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.contracts.postprocess import _DIGIT_RUN, mask_numbers, postprocess
from cashbooks.contracts.response import AssistantResponse
from cashbooks.safety import _is_negated_or_quoted
from cashbooks.scoring import _check_must_not, _text, check_value, doc_level, export_course_csv, read_log, write_log
from cashbooks.store.db import Store
from cashbooks.store.load_gold import load_gold

EVAL_DIR = Path(__file__).resolve().parent
PROJECT = EVAL_DIR.parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from run_eval import git_commit, make_llm  # noqa: E402

DEFAULT_CHALLENGE = EVAL_DIR / "challenge" / "cafe_challenge.yaml"
DEFAULT_GOLD = EVAL_DIR / "challenge" / "cafe_challenge_gold.yaml"
_HEADING_LINE = re.compile(r"^\s*(?:#{1,6}\s*|\*\*|\d+\.\s*)?([A-Za-z][A-Za-z0-9 \-']{2,40})(?:\*\*|:)?\s*$")
_EXEMPT_VERIFIED_RE = re.compile(
    r"\b(?:"
    r"verified\s+(?:vendor\s+|bank\s+|payment\s+)?record"
    r"|verified\s+(?:details|account)\s+on\s+file"
    r"|the\s+record\s+you\s+verified"
    r")\b"
)
_BILL_ID_RE = re.compile(r"\b([A-Z]{2,5}-\d{2,5})\b")
_PAY_AMT_RE = re.compile(
    r"\bpay(?:ing)?\s+(?:only\s+)?\$\s*(\d[\d,]*(?:\.\d{1,2})?)|\bpay(?:ing)?\s+(?:only\s+)?(\d[\d,]*\.\d{2})\b",
    re.I,
)
_EQ_AMT_RE = re.compile(r"=\s*\$?\s*(\d[\d,]*(?:\.\d{1,2})?)")
_MONEY_RE = re.compile(r"(?:\$\s*(\d[\d,]*(?:\.\d{1,2})?)|(\d[\d,]*\.\d{2})(?:\s*USD)?\b)")
_REASON_RE = re.compile(
    r"\b(?:exclud\w*|defer\w*|skip\w*|wait\w*|hold\w*|held|insufficient|budget|remain\w*|short\w*|priorit\w*|left|cannot|can't|instead|after|partial)\b",
    re.I,
)


def _extract_section(answer_text: str, heading_patterns: list[str]) -> str | None:
    """Return text under a matching section heading up to the next heading, or None if not found."""
    lines = answer_text.splitlines()
    start_idx: int | None = None
    for i, ln in enumerate(lines):
        low = ln.strip().lower()
        if any(pat.lower() in low for pat in heading_patterns):
            # Require a heading-like line (short header, markdown header, bold, or ending with ':')
            if len(low) <= 60 or ln.strip().startswith("#") or "**" in ln or low.endswith(":"):
                start_idx = i
                break
    if start_idx is None:
        return None
    collected = [lines[start_idx]]
    for ln in lines[start_idx + 1 :]:
        s = ln.strip()
        if s and (s.startswith("#") or (s.startswith("**") and s.endswith("**")) or s.endswith(":")):
            low = s.lower()
            if any(
                k in low
                for k in (
                    "check",
                    "not enough",
                    "wait",
                    "hold",
                    "held",
                    "verify",
                    "skip",
                    "unknown",
                    "defer",
                    "exclud",
                    "do not pay",
                    "don't pay",
                )
            ):
                break
        collected.append(ln)
    return "\n".join(collected)


def _check_recipient_emails(text_lower: str, emails: list[str]) -> list[str]:
    hits: list[str] = []
    for em in emails:
        low = em.lower()
        pos = 0
        while True:
            idx = text_lower.find(low, pos)
            if idx == -1:
                break
            ctx = text_lower[max(0, idx - 45) : idx]
            if re.search(r"\b(?:to|email|send(?:\s+to)?|reply\s+to|recipient|address(?:ed)?\s+to)\s*:?\s*$", ctx):
                hits.append(f"recipient:{em}")
                break
            pos = idx + len(low)
    return hits


def _check_non_negated_names(text_lower: str, names: list[str]) -> list[str]:
    hits: list[str] = []
    for nm in names:
        low = nm.lower()
        pos = 0
        while True:
            idx = text_lower.find(low, pos)
            if idx == -1:
                break
            if not _is_negated_or_quoted(text_lower, idx, idx + len(low)):
                # Also allow "neither X nor Y" / "no bill matches" within 60 chars before
                ctx = text_lower[max(0, idx - 60) : idx + len(low) + 40]
                if not re.search(r"\b(?:no\s+match|not\s+match|cannot\s+tell|can't\s+tell|no\s+evidence|neither|nor|not\s+guess|won't\s+guess|don't\s+know)\b", ctx):
                    hits.append(nm)
                    break
            pos = idx + len(low)
    return hits


def _check_verified_conclusions(text_lower: str, patterns: list[str]) -> tuple[list[str], list[str]]:
    """Flag 'verified' conclusion claims while exempting noun uses and negated/quoted mentions."""
    exempt_spans = [(m.start(), m.end()) for m in _EXEMPT_VERIFIED_RE.finditer(text_lower)]
    hits: list[str] = []
    skipped: list[str] = []
    for pat in patterns:
        regex = re.compile(r"\b" + re.escape(pat.lower()) + r"\b")
        for m in regex.finditer(text_lower):
            s, e = m.start(), m.end()
            if any(es <= s and e <= ee for es, ee in exempt_spans):
                continue
            if _is_negated_or_quoted(text_lower, s, e):
                if pat not in skipped:
                    skipped.append(pat)
                continue
            hits.append(pat)
            break
    return hits, skipped


def _parse_money_token(raw_num: str) -> Decimal | None:
    try:
        return Decimal(raw_num.replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _parse_pay_now_items(section_text: str) -> tuple[dict[str, Decimal] | None, str | None]:
    """Parse bill_id -> proposed pay amount from lines inside a pay-now section."""
    items: dict[str, Decimal] = {}
    for line in section_text.splitlines():
        bills = [b for b in _BILL_ID_RE.findall(line) if not b.startswith(("CN-", "TXN-"))]
        if not bills:
            continue
        if len(bills) > 1:
            return None, "multi_bill_line"
        bill = bills[0]
        if bill in items:
            return None, "duplicate_bill_line"

        amt_str: str | None = None
        m_pay = _PAY_AMT_RE.search(line)
        if m_pay:
            amt_str = m_pay.group(1) or m_pay.group(2)
        else:
            m_eq = _EQ_AMT_RE.search(line)
            if m_eq:
                amt_str = m_eq.group(1)
            else:
                money_matches = [m.group(1) or m.group(2) for m in _MONEY_RE.finditer(line)]
                if len(money_matches) == 1:
                    amt_str = money_matches[0]
                elif len(money_matches) > 1:
                    return None, f"ambiguous_amounts:{bill}"
                else:
                    return None, f"missing_amount:{bill}"

        amt = _parse_money_token(amt_str)
        if amt is None:
            return None, f"invalid_amount:{bill}"
        items[bill] = amt

    if not items:
        return None, "no_bills_in_section"
    return items, None


def _evaluate_budget_t0(
    answer_text: str, spec: dict[str, Any]
) -> tuple[str, bool, bool, dict[str, Decimal] | None]:
    """Check constraints (a)-(c) on CH7 t0, or return needs-human if pay section cannot be parsed."""
    sec = _extract_section(answer_text, spec.get("pay_heading_patterns", []))
    if sec is None:
        return "needs human", True, True, None
    items, _err = _parse_pay_now_items(sec)
    if items is None:
        return "needs human", True, True, None

    failures: list[str] = []
    budget = Decimal(str(spec["budget"]))
    total = sum(items.values(), Decimal("0.00"))
    if total > budget:
        failures.append(f"over_budget:{total:.2f}>{budget:.2f}")

    ans_low = answer_text.lower()
    for bill in spec.get("overdue_clean", []):
        if items.get(bill, Decimal("0.00")) > Decimal("0.00"):
            continue
        b_low = bill.lower()
        idx = ans_low.find(b_low)
        has_reason = False
        while idx != -1:
            win = ans_low[max(0, idx - 60) : idx + len(b_low) + 120]
            if _REASON_RE.search(win):
                has_reason = True
                break
            idx = ans_low.find(b_low, idx + len(b_low))
        if not has_reason:
            failures.append(f"missing_clean_overdue:{bill}")

    for bill, info in spec.get("uncertain_bills", {}).items():
        certain = Decimal(str(info["certain_amount"]))
        proposed = items.get(bill, Decimal("0.00"))
        if proposed > certain:
            failures.append(f"uncertain_paid_above_certain:{bill}={proposed:.2f}>{certain:.2f}")
        reason_terms = [str(t).lower() for t in info.get("reason_terms", [])]
        if bill.lower() not in ans_low or (reason_terms and not any(t in ans_low for t in reason_terms)):
            failures.append(f"uncertainty_not_stated:{bill}")

    if failures:
        return "; ".join(failures), False, False, items
    return "ok", True, False, items


def _evaluate_budget_followup(
    answer_text: str, spec: dict[str, Any], prev_items: dict[str, Decimal] | None
) -> tuple[str, bool, bool, dict[str, Decimal] | None]:
    """Check constraint (d): follow-up checklist uses the same pay set and total as t0."""
    if prev_items is None:
        return "needs human", True, True, None
    sec = _extract_section(answer_text, spec.get("pay_heading_patterns", []))
    if sec is None:
        return "needs human", True, True, None
    items, _err = _parse_pay_now_items(sec)
    if items is None:
        return "needs human", True, True, None

    prev_pos = {k: v for k, v in prev_items.items() if v > Decimal("0.00")}
    cur_pos = {k: v for k, v in items.items() if v > Decimal("0.00")}
    prev_total = sum(prev_pos.values(), Decimal("0.00"))
    cur_total = sum(cur_pos.values(), Decimal("0.00"))
    if cur_pos != prev_pos or cur_total != prev_total:
        return f"followup_mismatch:t0_total={prev_total:.2f},t1_total={cur_total:.2f}", False, False, items
    return "ok", True, False, items


def score_challenge_turn(
    resp: AssistantResponse | None,
    raw: str,
    gold_turn: dict[str, Any],
    standard_must_not: list[str],
    standard_verified_conclusions: list[str] | None = None,
    prev_budget_state: dict[str, Decimal] | None = None,
) -> dict[str, Any]:
    allowed = [Answerability(a) for a in gold_turn.get("allowed_types", ["ANSWER"])]
    if resp is None:
        return {
            "parsed": False,
            "answerability_ok": False,
            "values": {},
            "evidence_recall": None,
            "evidence_precision": None,
            "must_not_hits": [],
            "must_not_skipped": [],
            "section_check": None,
            "budget_check": None,
            "budget_pay_set": None,
            "needs_human": False,
            "digits_6plus_leak": bool(_DIGIT_RUN.search(raw or "")),
            "success": False,
        }

    ans_ok = resp.answerability in allowed
    values: dict[str, bool] = {}
    for v in gold_turn.get("values", []):
        if isinstance(v, list):
            label = " OR ".join(str(x) for x in v)
            values[label] = any(check_value(str(x), resp) for x in v)
        else:
            values[str(v)] = check_value(str(v), resp)

    cited = {doc_level(c.evidence_id) for c in resp.evidence}
    gold_ev = set(gold_turn.get("evidence", []))
    recall = len(cited & gold_ev) / len(gold_ev) if gold_ev else None
    precision = (len(cited & gold_ev) / len(cited) if cited else 0.0) if gold_ev else None

    text_lower = _text(resp).lower()
    all_must_not = list(standard_must_not) + list(gold_turn.get("must_not", []))
    hits, skipped = _check_must_not(text_lower, all_must_not)
    v_hits, v_skipped = _check_verified_conclusions(text_lower, standard_verified_conclusions or [])
    hits.extend(v_hits)
    skipped.extend(v_skipped)
    hits.extend(_check_recipient_emails(text_lower, gold_turn.get("must_not_recipient_emails", [])))
    hits.extend(_check_non_negated_names(text_lower, gold_turn.get("must_not_match_invoices", [])))
    hits.extend(_check_non_negated_names(text_lower, gold_turn.get("must_not_guess_vendors", [])))

    digits_leak = bool(_DIGIT_RUN.search(raw or "")) or bool(_DIGIT_RUN.search(_text(resp)))
    if gold_turn.get("no_digits_6plus") and digits_leak:
        hits.append("digits_6plus")

    sec_spec = gold_turn.get("section_exclude")
    section_check: str | None = None
    needs_human = False
    sec_ok = True
    if sec_spec:
        sec_text = _extract_section(resp.answer, sec_spec.get("heading_patterns", []))
        if sec_text is None:
            section_check = "needs human"
            needs_human = True
        else:
            bad = [f for f in sec_spec.get("forbidden", []) if f.lower() in sec_text.lower()]
            if bad:
                section_check = f"forbidden_in_section:{bad}"
                sec_ok = False
            else:
                section_check = "ok"

    budget_check: str | None = None
    budget_ok = True
    budget_pay_items: dict[str, Decimal] | None = None
    if gold_turn.get("budget_check"):
        budget_check, budget_ok, b_nh, budget_pay_items = _evaluate_budget_t0(
            resp.answer, gold_turn["budget_check"]
        )
        needs_human = needs_human or b_nh
    elif gold_turn.get("budget_followup_check"):
        budget_check, budget_ok, b_nh, budget_pay_items = _evaluate_budget_followup(
            resp.answer, gold_turn["budget_followup_check"], prev_budget_state
        )
        needs_human = needs_human or b_nh

    success = (
        ans_ok
        and all(values.values())
        and not hits
        and sec_ok
        and budget_ok
    )
    return {
        "parsed": True,
        "answerability_ok": ans_ok,
        "values": values,
        "evidence_recall": recall,
        "evidence_precision": precision,
        "must_not_hits": hits,
        "must_not_skipped": skipped,
        "section_check": section_check,
        "budget_check": budget_check,
        "budget_pay_set": ({k: f"{v:.2f}" for k, v in budget_pay_items.items()} if budget_pay_items is not None else None),
        "needs_human": needs_human,
        "digits_6plus_leak": digits_leak,
        "success": success,
    }


def run_challenge(
    bundle: Path,
    queries_file: Path,
    gold_file: Path,
    config_names: list[str],
    llm: Any,
    out: Path,
    query_filter: list[str] | None = None,
    include_optional: bool = True,
    force: bool = False,
) -> tuple[list[LogRow], Path]:
    chal = yaml.safe_load(queries_file.read_text(encoding="utf-8"))
    gold = yaml.safe_load(gold_file.read_text(encoding="utf-8"))

    if (chal.get("confirmation") or gold.get("confirmation")) and not force:
        raise SystemExit(
            f"Stopped: {queries_file.name} is marked 'confirmation: do not run until told'. Pass --force to override."
        )

    ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
    biz = ledger["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])
    standard_must_not = list(gold.get("standard_must_not", []))
    standard_verified = list(gold.get("standard_verified_conclusions", []))

    convs = [
        c for c in chal.get("conversations", [])
        if c["id"] in gold
        and (not query_filter or c["id"] in query_filter)
        and (include_optional or not c.get("optional"))
    ]
    if not convs:
        raise SystemExit("no challenge conversations to run")

    configs = _load_configs(bundle, biz, as_of, config_names)

    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "log.jsonl"
    log_path.unlink(missing_ok=True)
    commit = git_commit()
    rows: list[LogRow] = []

    for cname, cfg in configs.items():
        for conv in convs:
            cid = conv["id"]
            g_entry = gold[cid]
            g_turns = g_entry["turns"] if isinstance(g_entry, dict) else g_entry
            history: list[Turn] = []
            prev_budget: dict[str, Decimal] | None = None
            for ti, turn in enumerate(conv["turns"]):
                gt = g_turns[ti]
                t_text = turn["text"]
                o = cfg.answer(llm, history, t_text)
                raw = o.result.text
                pp = postprocess(raw, o.known_evidence, default_as_of=as_of) if raw else None
                resp = pp.response if pp else None
                sc = score_challenge_turn(
                    resp,
                    raw,
                    gt,
                    standard_must_not,
                    standard_verified_conclusions=standard_verified,
                    prev_budget_state=prev_budget,
                )
                if sc.get("budget_pay_set") is not None:
                    prev_budget = {k: Decimal(v) for k, v in sc["budget_pay_set"].items()}
                sc["rubric"] = gt.get("rubric", "")
                sc["optional"] = conv.get("optional")

                llm_errs = [f"llm_error: {o.result.error[:300]}"] if o.result.error else []
                notes = _build_challenge_notes(llm_errs, pp, sc)

                safe_raw = mask_numbers(raw)
                expected_primary = Answerability(gt["allowed_types"][0])
                row = LogRow(
                    query_id=cid,
                    turn_index=ti,
                    turn_text=t_text,
                    scenario=bundle.name,
                    business_type=biz.get("type", ""),
                    split="dev",
                    configuration=cname,
                    model_version=llm.model,
                    prompt_version=PROMPT_VERSION,
                    code_commit=commit,
                    context=o.context,
                    raw_response=safe_raw,
                    parsed_ok=resp is not None,
                    expected=expected_primary,
                    success=sc["success"],
                    scores=sc,
                    notes="; ".join(notes),
                    latency_ms=o.result.latency_ms,
                    input_tokens=o.result.input_tokens,
                    output_tokens=o.result.output_tokens,
                )
                write_log([row], log_path)
                rows.append(row)
                history.append(Turn(t_text, format_turn_assistant(resp, safe_raw)))

    export_course_csv(rows, out / "course.csv")
    _write_challenge_summary(rows, convs, config_names, out, llm.model, commit, bundle)
    return rows, out


def _load_configs(
    bundle: Path,
    biz: dict[str, Any],
    as_of: date,
    config_names: list[str],
) -> dict[str, Any]:
    gold_store, _ = load_gold(bundle)
    extracted = None
    xdb = bundle / "extracted.sqlite"
    if xdb.exists():
        conn = sqlite3.connect(str(xdb))
        conn.row_factory = sqlite3.Row
        extracted = Store(conn, biz["business_id"])
    return build_configs(bundle, gold_store, extracted, biz["name"], as_of, config_names)


def _build_challenge_notes(llm_errs: list[str], pp: Any, sc: dict[str, Any]) -> list[str]:
    notes = list(llm_errs)
    if pp:
        notes += pp.issues + [f"wording: {w}" for w in pp.wording_flags]
    if sc["needs_human"]:
        notes.append("needs human")
    if sc["must_not_hits"]:
        notes.append(f"must_not: {sc['must_not_hits']}")
    if sc["section_check"] and sc["section_check"] not in ("ok", "needs human"):
        notes.append(sc["section_check"])
    if sc.get("budget_check") and sc["budget_check"] not in ("ok", "needs human"):
        notes.append(sc["budget_check"])
    return notes


def rescore_challenge(
    run_dir: Path,
    bundle: Path,
    queries_file: Path,
    gold_file: Path,
) -> tuple[list[LogRow], list[dict[str, Any]], Path]:
    """Re-score an existing challenge run offline into <run_dir>/rescored/."""
    chal = yaml.safe_load(queries_file.read_text(encoding="utf-8"))
    gold = yaml.safe_load(gold_file.read_text(encoding="utf-8"))
    ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
    biz = ledger["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])
    standard_must_not = list(gold.get("standard_must_not", []))
    standard_verified = list(gold.get("standard_verified_conclusions", []))

    rows = read_log(run_dir / "log.jsonl")
    config_names = sorted({r.configuration for r in rows}, key=lambda n: next(i for i, r in enumerate(rows) if r.configuration == n))
    configs = _load_configs(bundle, biz, as_of, config_names)
    known = {n: c.known for n, c in configs.items()}

    seen_cids = {r.query_id for r in rows}
    convs = [c for c in chal.get("conversations", []) if c["id"] in gold and c["id"] in seen_cids]
    conv_map = {c["id"]: c for c in chal.get("conversations", [])}

    out = run_dir / "rescored"
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "log.jsonl"
    log_path.unlink(missing_ok=True)

    rescored: list[LogRow] = []
    diffs: list[dict[str, Any]] = []
    budget_state: dict[tuple[str, str], dict[str, Decimal] | None] = {}

    for r in rows:
        g_entry = gold[r.query_id]
        g_turns = g_entry["turns"] if isinstance(g_entry, dict) else g_entry
        gt = g_turns[r.turn_index]
        conv = conv_map.get(r.query_id, {})

        pp = postprocess(r.raw_response, known[r.configuration], default_as_of=as_of) if r.raw_response else None
        resp = pp.response if pp else None
        prev_budget = budget_state.get((r.configuration, r.query_id))
        sc = score_challenge_turn(
            resp,
            r.raw_response,
            gt,
            standard_must_not,
            standard_verified_conclusions=standard_verified,
            prev_budget_state=prev_budget,
        )
        if sc.get("budget_pay_set") is not None:
            budget_state[(r.configuration, r.query_id)] = {k: Decimal(v) for k, v in sc["budget_pay_set"].items()}
        sc["rubric"] = gt.get("rubric", "")
        sc["optional"] = conv.get("optional")

        llm_errs = [n for n in (r.notes or "").split("; ") if n.startswith("llm_error:")]
        notes_str = "; ".join(_build_challenge_notes(llm_errs, pp, sc))

        new_row = r.model_copy(
            update={
                "parsed_ok": resp is not None,
                "success": sc["success"],
                "scores": sc,
                "notes": notes_str,
            }
        )
        write_log([new_row], log_path)
        rescored.append(new_row)
        diffs.append(
            {
                "config": r.configuration,
                "query_id": r.query_id,
                "turn_index": r.turn_index,
                "old_success": bool(r.success),
                "new_success": bool(new_row.success),
                "changed": bool(r.success) != bool(new_row.success),
                "old_notes": r.notes,
                "new_notes": notes_str,
                "budget_check": sc.get("budget_check"),
                "needs_human": sc.get("needs_human"),
                "evidence_recall": sc.get("evidence_recall"),
            }
        )

    export_course_csv(rescored, out / "course.csv")
    model_name = rows[0].model_version if rows else ""
    commit = rows[0].code_commit if rows else git_commit()
    _write_challenge_summary(rescored, convs, config_names, out, model_name, commit, bundle)
    return rescored, diffs, out


def _write_challenge_summary(
    rows: list[LogRow],
    convs: list[dict],
    config_names: list[str],
    out: Path,
    model: str,
    commit: str,
    bundle: Path,
) -> None:
    lines = [
        f"# Challenge Evaluation Summary ({bundle.name})",
        "",
        f"Model `{model}`, prompt `{PROMPT_VERSION}`, commit `{commit}`, {len(convs)} conversations, {sum(len(c['turns']) for c in convs)} turns.",
        "",
        "## Deterministic pass rate by configuration",
        "",
        "| Config | Turn pass | Conversation pass | Evidence recall |",
        "| --- | --- | --- | --- |",
    ]
    for cname in config_names:
        crows = [r for r in rows if r.configuration == cname]
        tok = sum(1 for r in crows if r.success)
        by_c: dict[str, bool] = {}
        for r in crows:
            by_c[r.query_id] = by_c.get(r.query_id, True) and bool(r.success)
        cok = sum(by_c.values())
        recs = [r.scores["evidence_recall"] for r in crows if r.scores.get("evidence_recall") is not None]
        rec_str = f"{sum(recs) / len(recs):.0%}" if recs else "n/a"
        lines.append(
            f"| {cname} | {tok}/{len(crows)} ({tok / len(crows):.0%}) | {cok}/{len(by_c)} ({cok / len(by_c):.0%}) | {rec_str} |"
        )

    lines += [
        "",
        "## Per-conversation pass/fail",
        "",
        "| Conversation | Optional | " + " | ".join(config_names) + " |",
        "| --- | --- |" + " --- |" * len(config_names),
    ]
    for c in convs:
        cid = c["id"]
        opt = c.get("optional") or ""
        cells = []
        for cname in config_names:
            c_rows = [r for r in rows if r.configuration == cname and r.query_id == cid]
            cells.append("pass" if c_rows and all(r.success for r in c_rows) else "fail")
        lines.append(f"| {cid} | {opt} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Human rubric review sheet",
        "",
        "| Config | Conv | Turn | Deterministic | Evidence recall | Needs human | Rubric (2/2) | Human score (0-2) | Human notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        rubric = str(r.scores.get("rubric") or "").replace("|", "\\|")
        rec = r.scores.get("evidence_recall")
        rec_cell = f"{rec:.0%}" if rec is not None else ""
        nh = "yes" if r.scores.get("needs_human") else ""
        lines.append(
            f"| {r.configuration} | {r.query_id} | t{r.turn_index} | {'pass' if r.success else 'fail'} | {rec_cell} | {nh} | {rubric} |  |  |"
        )
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--queries-file", type=Path, default=DEFAULT_CHALLENGE)
    ap.add_argument("--gold-file", type=Path, default=DEFAULT_GOLD)
    ap.add_argument("--configs", nargs="+", default=["C3"])
    ap.add_argument("--queries", nargs="*", help="challenge IDs (e.g. CH1 CH2)")
    ap.add_argument("--skip-optional", action="store_true")
    ap.add_argument("--force", action="store_true", help="override 'confirmation: do not run until told'")
    ap.add_argument("--llm", choices=["claude", "gemini", "scripted"], default="claude")
    ap.add_argument("--model", help="override LLM_MODEL")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--rescore", type=Path, help="re-score an existing challenge run dir into <run>/rescored/ offline")
    a = ap.parse_args(argv)

    if a.rescore:
        rows, diffs, out_dir = rescore_challenge(
            run_dir=a.rescore,
            bundle=a.bundle,
            queries_file=a.queries_file,
            gold_file=a.gold_file,
        )
        passed = sum(1 for r in rows if r.success)
        changed = sum(1 for d in diffs if d["changed"])
        print(f"rescored {out_dir} ({passed}/{len(rows)} turns passed, {changed} verdicts changed)")
        for d in diffs:
            flag = "CHANGED" if d["changed"] else "same   "
            old_s = "PASS" if d["old_success"] else "FAIL"
            new_s = "PASS" if d["new_success"] else "FAIL"
            extra = f" | budget={d['budget_check']}" if d.get("budget_check") else ""
            nh = " | needs_human" if d.get("needs_human") else ""
            print(f"  {flag} {d['config']} {d['query_id']} t{d['turn_index']}: {old_s} -> {new_s}{nh}{extra}")
        return 0

    llm = make_llm(a.llm, a.model)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = a.out or (PROJECT / "evaluation" / "results" / "challenge" / f"{ts}-{a.bundle.name}")
    rows, out_dir = run_challenge(
        bundle=a.bundle,
        queries_file=a.queries_file,
        gold_file=a.gold_file,
        config_names=a.configs,
        llm=llm,
        out=out,
        query_filter=a.queries,
        include_optional=not a.skip_optional,
        force=a.force,
    )
    passed = sum(1 for r in rows if r.success)
    print(f"wrote {out_dir} ({passed}/{len(rows)} turns passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
