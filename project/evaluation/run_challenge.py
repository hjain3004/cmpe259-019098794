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
from pathlib import Path
from typing import Any

import yaml

from cashbooks.configs.answer import PROMPT_VERSION, Turn, build_configs, format_turn_assistant
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.contracts.postprocess import _DIGIT_RUN, mask_numbers, postprocess
from cashbooks.contracts.response import AssistantResponse
from cashbooks.safety import _is_negated_or_quoted
from cashbooks.scoring import _check_must_not, _text, check_value, doc_level, export_course_csv, write_log
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
            if any(k in low for k in ("check", "not enough", "wait", "hold", "verify", "skip", "unknown")):
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


def score_challenge_turn(
    resp: AssistantResponse | None,
    raw: str,
    gold_turn: dict[str, Any],
    standard_must_not: list[str],
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

    success = (
        ans_ok
        and all(values.values())
        and not hits
        and sec_ok
        and (recall is None or recall > 0)
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

    convs = [
        c for c in chal.get("conversations", [])
        if c["id"] in gold
        and (not query_filter or c["id"] in query_filter)
        and (include_optional or not c.get("optional"))
    ]
    if not convs:
        raise SystemExit("no challenge conversations to run")

    gold_store, _ = load_gold(bundle)
    extracted = None
    xdb = bundle / "extracted.sqlite"
    if xdb.exists():
        conn = sqlite3.connect(str(xdb))
        conn.row_factory = sqlite3.Row
        extracted = Store(conn, biz["business_id"])
    configs = build_configs(bundle, gold_store, extracted, biz["name"], as_of, config_names)

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
            for ti, turn in enumerate(conv["turns"]):
                gt = g_turns[ti]
                t_text = turn["text"]
                o = cfg.answer(llm, history, t_text)
                raw = o.result.text
                pp = postprocess(raw, o.known_evidence, default_as_of=as_of) if raw else None
                resp = pp.response if pp else None
                sc = score_challenge_turn(resp, raw, gt, standard_must_not)
                sc["rubric"] = gt.get("rubric", "")
                sc["optional"] = conv.get("optional")

                notes: list[str] = []
                if o.result.error:
                    notes.append(f"llm_error: {o.result.error[:300]}")
                if pp:
                    notes += pp.issues + [f"wording: {w}" for w in pp.wording_flags]
                if sc["needs_human"]:
                    notes.append("needs human")
                if sc["must_not_hits"]:
                    notes.append(f"must_not: {sc['must_not_hits']}")
                if sc["section_check"] and sc["section_check"] not in ("ok", "needs human"):
                    notes.append(sc["section_check"])

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
        "| Config | Turn pass | Conversation pass |",
        "| --- | --- | --- |",
    ]
    for cname in config_names:
        crows = [r for r in rows if r.configuration == cname]
        tok = sum(1 for r in crows if r.success)
        by_c: dict[str, bool] = {}
        for r in crows:
            by_c[r.query_id] = by_c.get(r.query_id, True) and bool(r.success)
        cok = sum(by_c.values())
        lines.append(f"| {cname} | {tok}/{len(crows)} ({tok / len(crows):.0%}) | {cok}/{len(by_c)} ({cok / len(by_c):.0%}) |")

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
        "| Config | Conv | Turn | Deterministic | Needs human | Rubric (2/2) | Human score (0-2) | Human notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        rubric = str(r.scores.get("rubric") or "").replace("|", "\\|")
        nh = "yes" if r.scores.get("needs_human") else ""
        lines.append(
            f"| {r.configuration} | {r.query_id} | t{r.turn_index} | {'pass' if r.success else 'fail'} | {nh} | {rubric} |  |  |"
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
    a = ap.parse_args(argv)

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
