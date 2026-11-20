"""Offline rescoring under frozen scorer_v3, writing exclusively under evaluation/results/scorer_v3/.

Preserves all historical runs, logs, summaries, and existing rescored directories untouched.
Generates:
  - Per-run rescored artifacts (log.jsonl, course.csv, summary.json, summary.md, metadata.json)
  - Per-turn change report (per_turn_changes.csv, per_turn_changes.md)
  - Aggregate per-stratum, per-configuration summary (aggregate_summary.json, aggregate_summary.md)
  - Challenge rescoring reconciliation (challenge_analysis.json, challenge_analysis.md)
  - Blinded human-review packet (human_review/blind_*.csv + separate key_*.csv, blank human labels)

Usage (from project/):
    ../.venv/bin/python evaluation/rescore_v3.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

EVAL_DIR = Path(__file__).resolve().parent
PROJECT = EVAL_DIR.parent
REPO_ROOT = PROJECT.parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from cashbooks.configs.answer import PROMPT_VERSION, build_configs  # noqa: E402
from cashbooks.contracts.evaluation import LogRow, QuerySuite  # noqa: E402
from cashbooks.contracts.postprocess import postprocess  # noqa: E402
from cashbooks.scoring import (  # noqa: E402
    SCORER_VERSION,
    _MONEY,
    _is_identifier,
    export_course_csv,
    read_log,
    score_turn,
    summarize,
    write_log,
    write_run_outputs,
)
from cashbooks.store.db import Store  # noqa: E402
from cashbooks.store.load_gold import load_gold  # noqa: E402
from run_challenge import _build_challenge_notes, score_challenge_turn  # noqa: E402

OUT_ROOT = PROJECT / "evaluation" / "results" / "scorer_v3"


@dataclass(frozen=True)
class RunSpec:
    stratum: str
    run_rel: str
    bundle_rel: str
    queries_rel: str = "evaluation/queries.yaml"
    use_prior_rescored: bool = False  # compare against prior <run>/rescored/log.jsonl when present


STANDARD_RUNS: list[RunSpec] = [
    # 1. Historical v1 core development (compare against latest prior rescored/ if present, else orig)
    RunSpec("historical_v1_core_dev", "evaluation/results/20261117-234352-cafe_01-claude-haiku-5-5", "data/dev/cafe_01", use_prior_rescored=True),
    RunSpec("historical_v1_core_dev", "evaluation/results/20261118-164027-cafe_01-claude-haiku-5-5", "data/dev/cafe_01", use_prior_rescored=True),
    RunSpec("historical_v1_core_dev", "evaluation/results/20261118-141745-plumbing_01-claude-haiku-5-5", "data/dev/plumbing_01", use_prior_rescored=True),
    RunSpec("historical_v1_core_dev", "evaluation/results/20261118-161549-plumbing_01-claude-haiku-5-5", "data/dev/plumbing_01", use_prior_rescored=True),
    # 2. Updated v2 core development
    RunSpec("v2_core_dev", "evaluation/results/20261118-223250-cafe_01-claude-haiku-5-5", "data/dev/cafe_01"),
    RunSpec("v2_core_dev", "evaluation/results/20261118-224539-plumbing_01-claude-haiku-5-5", "data/dev/plumbing_01"),
    # 3. Expanded v2 development
    RunSpec("v2_expanded_dev", "evaluation/results/20261118-231330-bakery_01-claude-haiku-5-5", "data/dev/bakery_01", "data/dev/bakery_01/queries.yaml"),
    RunSpec("v2_expanded_dev", "evaluation/results/20261118-232652-clinic_01-claude-haiku-5-5", "data/dev/clinic_01", "data/dev/clinic_01/queries.yaml"),
    # 4. v2 corpus scaling (same 21 cafe_01 conversations / 28 scored turns)
    RunSpec("v2_scaling", "evaluation/results/20261119-001330-cafe_01_x4-claude-haiku-5-5", "data/dev/cafe_01_x4"),
    RunSpec("v2_scaling", "evaluation/results/20261119-002636-cafe_01_x16-claude-haiku-5-5", "data/dev/cafe_01_x16"),
    # 5. v2 frozen held-out test set (rescored ONLY after scorer_v3 rules were frozen)
    RunSpec("v2_held_out", "evaluation/results/20261119-010517-landscaping_01-claude-haiku-5-5", "data/test/landscaping_01"),
]

CHALLENGE_RUNS: list[tuple[str, str, str, str]] = [
    (
        "20261119-103951-cafe_01",
        "evaluation/results/challenge/20261119-103951-cafe_01",
        "data/dev/cafe_01",
        "evaluation/challenge/cafe_challenge.yaml",
    ),
    (
        "20261119-110444-cafe_01",
        "evaluation/results/challenge/20261119-110444-cafe_01",
        "data/dev/cafe_01",
        "evaluation/challenge/cafe_challenge.yaml",
    ),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_info() -> tuple[str, bool]:
    try:
        head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True).strip())
        return head, dirty
    except Exception:
        return "unknown", True


def _diagnose_rule_cause(
    old_row: LogRow,
    new_row: LogRow,
    gold_values: dict[str, Any],
) -> tuple[str, list[str]]:
    causes: list[str] = []
    changed_keys: list[str] = []

    if old_row.parsed_ok != new_row.parsed_ok:
        causes.append(f"parse_changed:{old_row.parsed_ok}->{new_row.parsed_ok}")

    old_ans_ok = bool(old_row.scores.get("answerability_ok"))
    new_ans_ok = bool(new_row.scores.get("answerability_ok"))
    if old_ans_ok != new_ans_ok:
        causes.append(f"answerability_ok:{old_ans_ok}->{new_ans_ok}")

    old_vals = old_row.scores.get("values") or {}
    new_vals = new_row.scores.get("values") or {}
    for k in sorted(set(old_vals) | set(new_vals)):
        ov = old_vals.get(k)
        nv = new_vals.get(k)
        if ov != nv:
            exp = str(gold_values.get(k, ""))
            changed_keys.append(f"{k}={exp}({ov}->{nv})")
            if _MONEY.match(exp.strip()):
                causes.append(f"scorer_v3_money_rule:{k}")
            else:
                causes.append(f"scorer_v3_value_rule:{k}")

    old_hits = list(old_row.scores.get("must_not_hits") or [])
    new_hits = list(new_row.scores.get("must_not_hits") or [])
    if old_hits != new_hits:
        causes.append(f"must_not_changed:{old_hits}->{new_hits}")

    old_rec = old_row.scores.get("evidence_recall")
    new_rec = new_row.scores.get("evidence_recall")
    if old_rec != new_rec:
        causes.append(f"evidence_recall_changed:{old_rec}->{new_rec}")

    if not causes:
        causes.append("other_or_unchanged")
    return "; ".join(causes), changed_keys


def rescore_standard_run(spec: RunSpec, code_hashes: dict[str, str], git_head: str, git_dirty: bool) -> dict[str, Any]:
    run_dir = PROJECT / spec.run_rel
    bundle = PROJECT / spec.bundle_rel
    qpath = PROJECT / spec.queries_rel

    baseline_log = run_dir / "log.jsonl"
    baseline_source = "orig"
    if spec.use_prior_rescored and (run_dir / "rescored" / "log.jsonl").exists():
        baseline_log = run_dir / "rescored" / "log.jsonl"
        baseline_source = "prior_rescored"

    suite = QuerySuite.model_validate(yaml.safe_load(qpath.read_text(encoding="utf-8")))
    specs = {c.id: c for c in suite.conversations}
    gold = yaml.safe_load((bundle / "gold.yaml").read_text(encoding="utf-8"))
    ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
    biz = ledger["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])

    gold_store, _ = load_gold(bundle)
    conn = sqlite3.connect(str(bundle / "extracted.sqlite"))
    conn.row_factory = sqlite3.Row
    rows = read_log(baseline_log)
    names = sorted({r.configuration for r in rows})
    known = {
        n: c.known
        for n, c in build_configs(bundle, gold_store, Store(conn, biz["business_id"]), biz["name"], as_of, names).items()
    }
    conn.close()

    out_dir = OUT_ROOT / spec.stratum / run_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "log.jsonl").unlink(missing_ok=True)

    scored_new: list[LogRow] = []
    scored_old: list[LogRow] = []
    per_turn_changes: list[dict[str, Any]] = []
    all_turn_records: list[dict[str, Any]] = []

    for r in rows:
        cspec = specs[r.query_id]
        turn = cspec.turns[r.turn_index]
        if not turn.scored:
            write_log([r], out_dir / "log.jsonl")
            continue
        gi = sum(1 for t in cspec.turns[: r.turn_index] if t.scored)
        gold_entry = gold[r.query_id]
        gold_turns = list(gold_entry.get("turns", []) if isinstance(gold_entry, dict) else gold_entry)
        g = gold_turns[gi] if gi < len(gold_turns) else {}
        g_vals = g.get("values", {}) or {}
        pp = postprocess(r.raw_response, known[r.configuration], default_as_of=as_of) if r.raw_response else None
        resp = pp.response if pp else None
        sc = score_turn(
            resp,
            turn.expected,
            g_vals,
            g.get("evidence", []),
            list(turn.must_not) + list(g.get("must_not", [])),
        )
        notes = (
            [n for n in r.notes.split("; ") if n.startswith("llm_error")]
            + (pp.issues if pp else [])
            + ([f"wording: {w}" for w in pp.wording_flags] if pp else [])
            + [f"must_not_identifier: {p}" for p in sc.must_not_hits if _is_identifier(p)]
            + [f"skipped_must_not: {p}" for p in sc.must_not_skipped]
        )
        new_row = r.model_copy(
            update={
                "parsed_ok": resp is not None,
                "success": sc.success,
                "scores": sc.to_dict(),
                "notes": "; ".join(notes),
            }
        )
        write_log([new_row], out_dir / "log.jsonl")
        scored_old.append(r)
        scored_new.append(new_row)

        cause, changed_keys = _diagnose_rule_cause(r, new_row, g_vals)
        rec = {
            "stratum": spec.stratum,
            "run_id": run_dir.name,
            "scenario": r.scenario,
            "baseline_source": baseline_source,
            "configuration": r.configuration,
            "query_id": r.query_id,
            "turn_index": r.turn_index,
            "turn_text": r.turn_text,
            "expected_answerability": turn.expected.value,
            "expected_values": json.dumps(g_vals, sort_keys=True),
            "old_verdict": bool(r.success),
            "new_verdict": bool(new_row.success),
            "changed": bool(r.success) != bool(new_row.success),
            "rule_cause": cause,
            "changed_value_keys": "; ".join(changed_keys),
            "raw_response": r.raw_response,
            "old_notes": r.notes,
            "new_notes": new_row.notes,
        }
        all_turn_records.append(rec)
        if rec["changed"]:
            per_turn_changes.append(rec)

    meta_in = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    conv_ids = [q for q in gold if q in specs and q in {r.query_id for r in rows}]
    qlabels = {c.id: list(c.labels) for c in suite.conversations}
    prompt_ver = scored_new[0].prompt_version if scored_new else meta_in.get("prompt_version", PROMPT_VERSION)
    write_run_outputs(
        scored_new,
        out_dir,
        f"{meta_in['run']} ({SCORER_VERSION})",
        meta_in["model"],
        meta_in["commit"],
        str(bundle),
        conv_ids,
        len(scored_new) // len(names),
        prompt_ver,
        query_labels=qlabels,
    )

    old_sum = summarize(scored_old)
    new_sum = summarize(scored_new)
    per_cfg: dict[str, dict[str, Any]] = {}
    for cfg in names:
        c_recs = [x for x in all_turn_records if x["configuration"] == cfg]
        p2f = sum(1 for x in c_recs if x["old_verdict"] and not x["new_verdict"])
        f2p = sum(1 for x in c_recs if (not x["old_verdict"]) and x["new_verdict"])
        per_cfg[cfg] = {
            "turns": new_sum[cfg]["turns"],
            "old_successes": old_sum[cfg]["successes"],
            "old_rate": old_sum[cfg]["success_rate"],
            "new_successes": new_sum[cfg]["successes"],
            "new_rate": new_sum[cfg]["success_rate"],
            "delta_turns": new_sum[cfg]["successes"] - old_sum[cfg]["successes"],
            "pass_to_fail": p2f,
            "fail_to_pass": f2p,
            "old_parsed": old_sum[cfg]["parsed"],
            "new_parsed": new_sum[cfg]["parsed"],
        }

    metadata = {
        "stratum": spec.stratum,
        "original_run_path": spec.run_rel,
        "baseline_log_compared": str(baseline_log.relative_to(PROJECT)),
        "baseline_source": baseline_source,
        "bundle": spec.bundle_rel,
        "queries_file": spec.queries_rel,
        "model_version": meta_in["model"],
        "prompt_version": prompt_ver,
        "original_code_commit": meta_in["commit"],
        "scorer_version": SCORER_VERSION,
        "code_hashes": code_hashes,
        "git_head": git_head,
        "git_dirty": git_dirty,
        "total_scored_turns_all_configs": len(scored_new),
        "verdict_changes_count": len(per_turn_changes),
        "per_config": per_cfg,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {
        "metadata": metadata,
        "changes": per_turn_changes,
        "all_records": all_turn_records,
    }


def rescore_challenge_runs(code_hashes: dict[str, str], git_head: str, git_dirty: bool) -> dict[str, Any]:
    gold_path = PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml"
    gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))
    standard_must_not = list(gold.get("standard_must_not", []))
    standard_verified = list(gold.get("standard_verified_conclusions", []))

    bundle = PROJECT / "data" / "dev" / "cafe_01"
    ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
    biz = ledger["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])
    gold_store, _ = load_gold(bundle)
    conn = sqlite3.connect(str(bundle / "extracted.sqlite"))
    conn.row_factory = sqlite3.Row
    ext_store = Store(conn, biz["business_id"])
    configs_known = {
        n: c.known
        for n, c in build_configs(bundle, gold_store, ext_store, biz["name"], as_of, ["C0", "C1", "C2", "C3", "C4"]).items()
    }
    conn.close()

    results: dict[str, Any] = {}
    all_challenge_changes: list[dict[str, Any]] = []
    all_challenge_records: list[dict[str, Any]] = []

    for label, run_rel, bundle_rel, queries_rel in CHALLENGE_RUNS:
        run_dir = PROJECT / run_rel
        orig_log = run_dir / "log.jsonl"
        if not orig_log.exists():
            continue
        orig_rows = read_log(orig_log)
        prior_rescored_path = run_dir / "rescored" / "log.jsonl"
        prior_rescored_rows = read_log(prior_rescored_path) if prior_rescored_path.exists() else None
        prior_by_key = (
            {(r.configuration, r.query_id, r.turn_index): r for r in prior_rescored_rows}
            if prior_rescored_rows
            else {}
        )

        out_dir = OUT_ROOT / "challenge_cafe" / label
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "log.jsonl").unlink(missing_ok=True)

        v3_rows: list[LogRow] = []
        turn_comparisons: list[dict[str, Any]] = []
        budget_state: dict[tuple[str, str], dict[str, Decimal] | None] = {}

        for r in orig_rows:
            g_entry = gold[r.query_id]
            g_turns = g_entry["turns"] if isinstance(g_entry, dict) else g_entry
            gt = g_turns[r.turn_index]
            pp = postprocess(r.raw_response, configs_known[r.configuration], default_as_of=as_of) if r.raw_response else None
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
            write_log([new_row], out_dir / "log.jsonl")
            v3_rows.append(new_row)

            pr = prior_by_key.get((r.configuration, r.query_id, r.turn_index))
            orig_ok = bool(r.success)
            prior_ok = bool(pr.success) if pr is not None else None
            v3_ok = bool(new_row.success)

            # Identify exact difference causes between orig, prior_rescored, and v3
            orig_vals = r.scores.get("values") or {}
            prior_vals = (pr.scores.get("values") or {}) if pr is not None else {}
            v3_vals = new_row.scores.get("values") or {}

            comp = {
                "run_id": label,
                "configuration": r.configuration,
                "query_id": r.query_id,
                "turn_index": r.turn_index,
                "turn_text": r.turn_text,
                "orig_success": orig_ok,
                "prior_rescored_success": prior_ok,
                "scorer_v3_success": v3_ok,
                "orig_ans_ok": r.scores.get("answerability_ok"),
                "prior_ans_ok": pr.scores.get("answerability_ok") if pr is not None else None,
                "v3_ans_ok": new_row.scores.get("answerability_ok"),
                "orig_values": orig_vals,
                "prior_values": prior_vals,
                "v3_values": v3_vals,
                "orig_must_not": r.scores.get("must_not_hits"),
                "prior_must_not": pr.scores.get("must_not_hits") if pr is not None else None,
                "v3_must_not": new_row.scores.get("must_not_hits"),
                "raw_response": r.raw_response,
            }
            turn_comparisons.append(comp)

            base_ok = prior_ok if prior_ok is not None else orig_ok
            base_src = "prior_rescored" if prior_ok is not None else "orig"
            changed_keys = []
            base_vals = prior_vals if prior_ok is not None else orig_vals
            for k in sorted(set(base_vals) | set(v3_vals)):
                if base_vals.get(k) != v3_vals.get(k):
                    changed_keys.append(f"{k}({base_vals.get(k)}->{v3_vals.get(k)})")

            cause = "unchanged"
            if base_ok != v3_ok:
                cause = "challenge_scorer_v3_money_or_sign_rule" if changed_keys else "challenge_evaluator_or_gold_rule"
            rec = {
                "stratum": "challenge_cafe",
                "run_id": label,
                "scenario": r.scenario,
                "baseline_source": base_src,
                "configuration": r.configuration,
                "query_id": r.query_id,
                "turn_index": r.turn_index,
                "turn_text": r.turn_text,
                "expected_answerability": "/".join(gt.get("allowed_types", ["ANSWER"])),
                "expected_values": json.dumps(gt.get("values", [])),
                "old_verdict": base_ok,
                "new_verdict": v3_ok,
                "changed": base_ok != v3_ok,
                "rule_cause": cause,
                "changed_value_keys": "; ".join(changed_keys),
                "raw_response": r.raw_response,
                "old_notes": (pr.notes if pr is not None else r.notes),
                "new_notes": new_row.notes,
            }
            all_challenge_records.append(rec)
            if rec["changed"]:
                all_challenge_changes.append(rec)

        export_course_csv(v3_rows, out_dir / "course.csv")
        orig_pass = sum(1 for r in orig_rows if r.success)
        prior_pass = sum(1 for r in prior_rescored_rows if r.success) if prior_rescored_rows else None
        v3_pass = sum(1 for r in v3_rows if r.success)
        meta = {
            "stratum": "challenge_cafe",
            "original_run_path": run_rel,
            "bundle": bundle_rel,
            "queries_file": queries_rel,
            "gold_file": "evaluation/challenge/cafe_challenge_gold.yaml",
            "model_version": orig_rows[0].model_version if orig_rows else "",
            "prompt_version": orig_rows[0].prompt_version if orig_rows else PROMPT_VERSION,
            "original_code_commit": orig_rows[0].code_commit if orig_rows else "",
            "scorer_version": SCORER_VERSION,
            "code_hashes": code_hashes,
            "git_head": git_head,
            "git_dirty": git_dirty,
            "turns": len(orig_rows),
            "orig_passed": orig_pass,
            "prior_rescored_passed": prior_pass,
            "scorer_v3_passed": v3_pass,
        }
        (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        results[label] = {"metadata": meta, "turns": turn_comparisons}

    (OUT_ROOT / "challenge_analysis.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    # Write markdown analysis
    md = [
        "# Challenge Rescoring Reconciliation (`cafe_01`, `CH1`–`CH7`)",
        "",
        "Historical challenge runs are preserved untouched. This report compares original saved `log.jsonl`, existing `<run>/rescored/log.jsonl` (where present), and `scorer_v3` using the exact same saved `raw_response` strings (zero model calls).",
        "",
    ]
    for label, info in results.items():
        m = info["metadata"]
        prior_str = f"{m['prior_rescored_passed']}/{m['turns']}" if m["prior_rescored_passed"] is not None else "n/a"
        md += [
            f"## Run `{label}`",
            f"- Original path: `{m['original_run_path']}`",
            f"- Model: `{m['model_version']}`, prompt: `{m['prompt_version']}`, original commit: `{m['original_code_commit']}`",
            f"- Original `log.jsonl`: **{m['orig_passed']}/{m['turns']}**",
            f"- Prior `rescored/log.jsonl`: **{prior_str}**",
            f"- Under `scorer_v3`: **{m['scorer_v3_passed']}/{m['turns']}**",
            "",
            "| Config | Query | Turn | Orig | Prior Rescored | `scorer_v3` | Key Differences |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for t in info["turns"]:
            if (
                t["orig_success"] != t["scorer_v3_success"]
                or (t["prior_rescored_success"] is not None and t["orig_success"] != t["prior_rescored_success"])
                or (t["prior_rescored_success"] is not None and t["prior_rescored_success"] != t["scorer_v3_success"])
            ):
                diffs = []
                if t["orig_ans_ok"] != t["v3_ans_ok"]:
                    diffs.append(f"ans_ok:{t['orig_ans_ok']}->{t['v3_ans_ok']}")
                if t["orig_values"] != t["v3_values"]:
                    diffs.append(f"orig_vals={t['orig_values']} vs v3_vals={t['v3_values']}")
                if t["prior_values"] and t["prior_values"] != t["v3_values"]:
                    diffs.append(f"prior_vals={t['prior_values']} vs v3_vals={t['v3_values']}")
                if t["orig_must_not"] != t["v3_must_not"]:
                    diffs.append(f"must_not:{t['orig_must_not']}->{t['v3_must_not']}")
                p_str = "n/a" if t["prior_rescored_success"] is None else ("PASS" if t["prior_rescored_success"] else "FAIL")
                md.append(
                    f"| {t['configuration']} | {t['query_id']} | t{t['turn_index']} | "
                    f"{'PASS' if t['orig_success'] else 'FAIL'} | {p_str} | "
                    f"{'PASS' if t['scorer_v3_success'] else 'FAIL'} | {'; '.join(diffs)} |"
                )
        md.append("")
    (OUT_ROOT / "challenge_analysis.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"results": results, "changes": all_challenge_changes, "all_records": all_challenge_records}


def _extract_display_reply(raw: str) -> str:
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            parts = [
                f"Type: {data.get('answerability')}",
                f"Answer: {data.get('answer')}",
            ]
            if data.get("clarifying_question"):
                parts.append(f"Clarifying question: {data.get('clarifying_question')}")
            if data.get("calculation"):
                parts.append(f"Calculation: {json.dumps(data.get('calculation'))}")
            if data.get("risk_indicators"):
                parts.append(f"Risk indicators: {json.dumps(data.get('risk_indicators'))}")
            if data.get("next_step"):
                parts.append(f"Next step: {data.get('next_step')}")
            return "\n".join(parts)
    except Exception:
        pass
    return raw[:1200]


def write_human_review_packet(all_records: list[dict[str, Any]], changes: list[dict[str, Any]], seed: int = 259) -> dict[str, int]:
    rev_dir = OUT_ROOT / "human_review"
    rev_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    # 1. Verdict-changing cases (all of them, shuffled, config & automated verdicts hidden in blind CSV)
    changed_list = list(changes)
    rng.shuffle(changed_list)
    blind_chg_fields = [
        "sample_id", "stratum", "scenario", "query_id", "turn_index", "turn_text",
        "expected_answerability", "expected_values", "displayed_reply",
        "human_verdict", "human_notes",
    ]
    key_chg_fields = [
        "sample_id", "stratum", "run_id", "baseline_source", "configuration",
        "query_id", "turn_index", "old_verdict", "new_verdict", "rule_cause", "changed_value_keys",
    ]
    with open(rev_dir / "blind_verdict_changes.csv", "w", newline="", encoding="utf-8") as bf, \
         open(rev_dir / "key_verdict_changes.csv", "w", newline="", encoding="utf-8") as kf:
        bw = csv.DictWriter(bf, fieldnames=blind_chg_fields)
        kw = csv.DictWriter(kf, fieldnames=key_chg_fields)
        bw.writeheader()
        kw.writeheader()
        for idx, rec in enumerate(changed_list, 1):
            sid = f"CHG-{idx:03d}"
            bw.writerow({
                "sample_id": sid,
                "stratum": rec["stratum"],
                "scenario": rec["scenario"],
                "query_id": rec["query_id"],
                "turn_index": rec["turn_index"],
                "turn_text": rec["turn_text"],
                "expected_answerability": rec["expected_answerability"],
                "expected_values": rec["expected_values"],
                "displayed_reply": _extract_display_reply(rec["raw_response"]),
                "human_verdict": "",
                "human_notes": "",
            })
            kw.writerow({
                "sample_id": sid,
                "stratum": rec["stratum"],
                "run_id": rec["run_id"],
                "baseline_source": rec["baseline_source"],
                "configuration": rec["configuration"],
                "query_id": rec["query_id"],
                "turn_index": rec["turn_index"],
                "old_verdict": rec["old_verdict"],
                "new_verdict": rec["new_verdict"],
                "rule_cause": rec["rule_cause"],
                "changed_value_keys": rec["changed_value_keys"],
            })

    # 2. Stratified sample of unchanged results across strata and pass/fail (40 items target, seed 259)
    unchanged = [r for r in all_records if not r["changed"]]
    buckets: dict[tuple[str, bool], list[dict[str, Any]]] = {}
    for r in unchanged:
        buckets.setdefault((r["stratum"], bool(r["new_verdict"])), []).append(r)

    sampled: list[dict[str, Any]] = []
    # Draw up to 4 per (stratum, pass/fail) bucket, deterministically sorted first
    for bkey in sorted(buckets):
        items = sorted(
            buckets[bkey],
            key=lambda x: (x["run_id"], x["configuration"], x["query_id"], x["turn_index"]),
        )
        rng.shuffle(items)
        sampled.extend(items[:4])
    rng.shuffle(sampled)

    with open(rev_dir / "blind_unchanged_sample.csv", "w", newline="", encoding="utf-8") as bf, \
         open(rev_dir / "key_unchanged_sample.csv", "w", newline="", encoding="utf-8") as kf:
        bw = csv.DictWriter(bf, fieldnames=blind_chg_fields)
        kw = csv.DictWriter(kf, fieldnames=key_chg_fields)
        bw.writeheader()
        kw.writeheader()
        for idx, rec in enumerate(sampled, 1):
            sid = f"UNC-{idx:03d}"
            bw.writerow({
                "sample_id": sid,
                "stratum": rec["stratum"],
                "scenario": rec["scenario"],
                "query_id": rec["query_id"],
                "turn_index": rec["turn_index"],
                "turn_text": rec["turn_text"],
                "expected_answerability": rec["expected_answerability"],
                "expected_values": rec["expected_values"],
                "displayed_reply": _extract_display_reply(rec["raw_response"]),
                "human_verdict": "",
                "human_notes": "",
            })
            kw.writerow({
                "sample_id": sid,
                "stratum": rec["stratum"],
                "run_id": rec["run_id"],
                "baseline_source": rec["baseline_source"],
                "configuration": rec["configuration"],
                "query_id": rec["query_id"],
                "turn_index": rec["turn_index"],
                "old_verdict": rec["old_verdict"],
                "new_verdict": rec["new_verdict"],
                "rule_cause": rec["rule_cause"],
                "changed_value_keys": rec["changed_value_keys"],
            })

    readme = [
        "# Blinded Human-Review Packet (`scorer_v3`)",
        "",
        "Both blind CSVs hide configuration (`C0`–`C4`), run ID, and automated verdicts (`old_verdict`, `new_verdict`).",
        "The separate key files (`key_verdict_changes.csv`, `key_unchanged_sample.csv`) must remain unopened until human review is finished.",
        "",
        f"- `blind_verdict_changes.csv`: **{len(changed_list)}** turns where verdicts changed under `scorer_v3`.",
        f"- `blind_unchanged_sample.csv`: **{len(sampled)}** stratified unchanged turns (up to 4 per `(stratum, pass/fail)` bucket, seed `259`).",
        "",
        "## Instructions for Human Reviewer",
        "1. Open `blind_verdict_changes.csv` and `blind_unchanged_sample.csv` only.",
        "2. For each row, enter `PASS` or `FAIL` in `human_verdict` based on whether `displayed_reply` accurately and safely answers `turn_text` given the bundle records.",
        "3. Record any edge-case observations (e.g., entity-value swap, contradictory prose, defensible reply-type boundary) in `human_notes`.",
        "4. Only after completing all rows, join by `sample_id` against the corresponding `key_*.csv` to compute scorer-vs-human agreement.",
    ]
    (rev_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    return {"verdict_changes": len(changed_list), "unchanged_sample": len(sampled)}


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    git_head, git_dirty = _git_info()
    code_hashes = {
        "scoring.py": _sha256(PROJECT / "code" / "src" / "cashbooks" / "scoring.py"),
        "postprocess.py": _sha256(PROJECT / "code" / "src" / "cashbooks" / "contracts" / "postprocess.py"),
        "rescore_v3.py": _sha256(Path(__file__).resolve()),
    }

    all_changes: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    by_stratum: dict[str, list[dict[str, Any]]] = {}

    for spec in STANDARD_RUNS:
        if not (PROJECT / spec.run_rel / "log.jsonl").exists():
            continue
        res = rescore_standard_run(spec, code_hashes, git_head, git_dirty)
        by_stratum.setdefault(spec.stratum, []).append(res["metadata"])
        all_changes.extend(res["changes"])
        all_records.extend(res["all_records"])

    chal_out = rescore_challenge_runs(code_hashes, git_head, git_dirty)
    all_changes.extend(chal_out["changes"])
    all_records.extend(chal_out["all_records"])

    # Per-turn change CSV and Markdown
    chg_fields = [
        "stratum", "run_id", "scenario", "baseline_source", "configuration",
        "query_id", "turn_index", "old_verdict", "new_verdict", "rule_cause",
        "changed_value_keys", "expected_values",
    ]
    with open(OUT_ROOT / "per_turn_changes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=chg_fields)
        w.writeheader()
        for c in all_changes:
            w.writerow({k: c[k] for k in chg_fields})

    chg_md = [
        f"# Per-Turn Verdict Changes Under `{SCORER_VERSION}`",
        "",
        f"Total verdict-changing turns across all rescored strata: **{len(all_changes)}**.",
        "",
        "| Stratum | Run | Config | Query | Turn | Baseline | Old | New | Cause | Changed Values |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in all_changes:
        chg_md.append(
            f"| {c['stratum']} | `{c['run_id']}` | {c['configuration']} | {c['query_id']} | t{c['turn_index']} | "
            f"{c['baseline_source']} | {'PASS' if c['old_verdict'] else 'FAIL'} | "
            f"{'PASS' if c['new_verdict'] else 'FAIL'} | `{c['rule_cause']}` | `{c['changed_value_keys']}` |"
        )
    (OUT_ROOT / "per_turn_changes.md").write_text("\n".join(chg_md) + "\n", encoding="utf-8")

    # Aggregate summary per stratum (NEVER pooling across strata)
    agg: dict[str, Any] = {
        "scorer_version": SCORER_VERSION,
        "git_head": git_head,
        "git_dirty": git_dirty,
        "code_hashes": code_hashes,
        "strata": {},
        "challenge": {k: v["metadata"] for k, v in chal_out["results"].items()},
    }
    agg_md = [
        f"# Aggregate `scorer_v3` Rescoring Summary (Separate Strata)",
        "",
        f"Scorer: `{SCORER_VERSION}` | Git HEAD: `{git_head}` | Working tree dirty: `{git_dirty}`",
        "",
    ]
    for stratum, metas in by_stratum.items():
        # Per-stratum aggregate across runs within the SAME stratum only
        stratum_cfg: dict[str, dict[str, int]] = {}
        for m in metas:
            for cfg, st in m["per_config"].items():
                cur = stratum_cfg.setdefault(cfg, {"turns": 0, "old": 0, "new": 0, "p2f": 0, "f2p": 0})
                cur["turns"] += st["turns"]
                cur["old"] += st["old_successes"]
                cur["new"] += st["new_successes"]
                cur["p2f"] += st["pass_to_fail"]
                cur["f2p"] += st["fail_to_pass"]
        agg["strata"][stratum] = {"runs": metas, "stratum_totals": stratum_cfg}

        agg_md += [
            f"## Stratum: `{stratum}`",
            "",
            "Runs included: " + ", ".join(f"`{m['original_run_path']}` (baseline: `{m['baseline_source']}`)" for m in metas),
            "",
            "| Config | Old Success | `scorer_v3` Success | Delta | Pass→Fail | Fail→Pass |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for cfg in sorted(stratum_cfg):
            c = stratum_cfg[cfg]
            t = c["turns"] or 1
            agg_md.append(
                f"| {cfg} | {c['old']}/{c['turns']} ({c['old']/t:.1%}) | "
                f"{c['new']}/{c['turns']} ({c['new']/t:.1%}) | {c['new']-c['old']:+d} | "
                f"{c['p2f']} | {c['f2p']} |"
            )
        agg_md.append("")

    (OUT_ROOT / "aggregate_summary.json").write_text(json.dumps(agg, indent=2) + "\n", encoding="utf-8")
    (OUT_ROOT / "aggregate_summary.md").write_text("\n".join(agg_md) + "\n", encoding="utf-8")

    rev_counts = write_human_review_packet(all_records, all_changes, seed=259)
    print(f"scorer_v3 rescoring complete: {len(all_records)} turns evaluated, {len(all_changes)} verdict changes.")
    print(f"human review packet: {rev_counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
