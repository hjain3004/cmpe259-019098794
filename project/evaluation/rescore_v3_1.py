"""Offline rescoring under scorer_v3_1 sharing cashbooks.eval_specs with evaluation/run_eval.py.

Supports explicit policy selection:
  --policy strict_historical  -> writes primary strict historical verdicts to evaluation/results/scorer_v3_1_strict/
  --policy with_specs         -> writes primary with_specs_v3_1 verdicts to evaluation/results/scorer_v3_1_with_specs/

Preserves all historical runs, existing rescored/ directories, evaluation/results/scorer_v3/,
and evaluation/results/scorer_v3_1/ untouched.

Usage (from project/):
    ../.venv/bin/python evaluation/rescore_v3_1.py --policy with_specs
    ../.venv/bin/python evaluation/rescore_v3_1.py --policy strict_historical
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

EVAL_DIR = Path(__file__).resolve().parent
PROJECT = EVAL_DIR.parent
REPO_ROOT = PROJECT.parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from cashbooks.configs.answer import PROMPT_VERSION, build_configs  # noqa: E402
from cashbooks.contracts.common import Answerability  # noqa: E402
from cashbooks.contracts.evaluation import LogRow, QuerySuite  # noqa: E402
from cashbooks.contracts.postprocess import postprocess  # noqa: E402
from cashbooks.contracts.response import AssistantResponse  # noqa: E402
from cashbooks.eval_specs import (  # noqa: E402
    DEFAULT_POLICY,
    LoadedEvalSpec,
    apply_turn_overrides,
    build_run_metadata,
    git_state,
    load_eval_spec,
    sha256_file,
)
from cashbooks.scoring import (  # noqa: E402
    SCORER_VERSION,
    _DATE,
    _MONEY,
    _PARTIAL_RE,
    _UNPAID_RE,
    _check_must_not,
    _is_identifier,
    _match_overpaid,
    _match_paid,
    _text,
    check_sign_only_mismatch,
    date_variants,
    doc_level,
    export_course_csv,
    money_variants,
    read_log,
    score_turn,
    write_log,
    write_run_outputs,
)
from cashbooks.store.db import Store  # noqa: E402
from cashbooks.store.load_gold import load_gold  # noqa: E402
from run_challenge import _build_challenge_notes, score_challenge_turn  # noqa: E402

DEFAULT_SPEC_PATH = PROJECT / "evaluation" / "specs_v3_1" / "amount_semantics_overrides.yaml"


@dataclass(frozen=True)
class RunSpec:
    stratum: str
    run_rel: str
    bundle_rel: str
    queries_rel: str = "evaluation/queries.yaml"
    use_prior_rescored: bool = False


STANDARD_RUNS: list[RunSpec] = [
    RunSpec("historical_v1_core_dev", "evaluation/results/20261117-234352-cafe_01-claude-haiku-5-5", "data/dev/cafe_01", use_prior_rescored=True),
    RunSpec("historical_v1_core_dev", "evaluation/results/20261118-164027-cafe_01-claude-haiku-5-5", "data/dev/cafe_01", use_prior_rescored=True),
    RunSpec("historical_v1_core_dev", "evaluation/results/20261118-141745-plumbing_01-claude-haiku-5-5", "data/dev/plumbing_01", use_prior_rescored=True),
    RunSpec("historical_v1_core_dev", "evaluation/results/20261118-161549-plumbing_01-claude-haiku-5-5", "data/dev/plumbing_01", use_prior_rescored=True),
    RunSpec("v2_core_dev", "evaluation/results/20261118-223250-cafe_01-claude-haiku-5-5", "data/dev/cafe_01"),
    RunSpec("v2_core_dev", "evaluation/results/20261118-224539-plumbing_01-claude-haiku-5-5", "data/dev/plumbing_01"),
    RunSpec("v2_expanded_dev", "evaluation/results/20261118-231330-bakery_01-claude-haiku-5-5", "data/dev/bakery_01", "data/dev/bakery_01/queries.yaml"),
    RunSpec("v2_expanded_dev", "evaluation/results/20261118-232652-clinic_01-claude-haiku-5-5", "data/dev/clinic_01", "data/dev/clinic_01/queries.yaml"),
    RunSpec("v2_scaling", "evaluation/results/20261119-001330-cafe_01_x4-claude-haiku-5-5", "data/dev/cafe_01_x4"),
    RunSpec("v2_scaling", "evaluation/results/20261119-002636-cafe_01_x16-claude-haiku-5-5", "data/dev/cafe_01_x16"),
    RunSpec("v2_held_out", "evaluation/results/20261119-010517-landscaping_01-claude-haiku-5-5", "data/test/landscaping_01"),
]

CHALLENGE_RUNS: list[tuple[str, str, str, str]] = [
    ("20261119-103951-cafe_01", "evaluation/results/challenge/20261119-103951-cafe_01", "data/dev/cafe_01", "evaluation/challenge/cafe_challenge.yaml"),
    ("20261119-110444-cafe_01", "evaluation/results/challenge/20261119-110444-cafe_01", "data/dev/cafe_01", "evaluation/challenge/cafe_challenge.yaml"),
]


def _legacy_check_value(expected: str, resp: AssistantResponse) -> bool:
    """Exact reconstruction of pre-v3 check_value (for Comparison A under identical postprocessing)."""
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
    if re.fullmatch(r"\d+(\.\d+)?", exp):
        return re.search(rf"(?<![\d.]){re.escape(exp)}(?![\d])", text) is not None
    if exp in ("yes", "no"):
        return re.search(rf"\b{exp}\b", text.lower()) is not None
    if exp in ("unpaid", "open"):
        return _UNPAID_RE.search(text) is not None
    if exp in ("partially paid", "partly paid", "partial"):
        return _PARTIAL_RE.search(text) is not None
    if exp == "paid":
        return _match_paid(text)
    if exp == "overpaid":
        return _match_overpaid(text)
    return exp in text.lower()


def _legacy_score_turn(
    resp: AssistantResponse | None,
    expected: Answerability,
    gold_values: dict,
    gold_evidence: list[str],
    must_not: list[str],
) -> tuple[bool, dict[str, bool]]:
    if resp is None:
        return False, {}
    ans_ok = resp.answerability == expected
    values = {k: _legacy_check_value(str(v), resp) for k, v in (gold_values or {}).items()}
    cited = {doc_level(c.evidence_id) for c in resp.evidence}
    gold = set(gold_evidence or [])
    recall = len(cited & gold) / len(gold) if gold else None
    hits, _ = _check_must_not(_text(resp).lower(), must_not)
    success = ans_ok and all(values.values()) and not hits and (recall is None or recall > 0)
    return success, values


def rescore_single_run(
    *,
    run_dir: Path,
    bundle: Path,
    queries_path: Path,
    out_dir: Path,
    policy: str,
    spec_path: Path | None,
    stratum: str = "custom",
    use_prior_rescored: bool = False,
) -> dict[str, Any]:
    """Rescore a single saved run under the selected primary policy using shared cashbooks.eval_specs."""
    gold_path = bundle / "gold.yaml"
    baseline_log = run_dir / "log.jsonl"
    baseline_source = "orig"
    if use_prior_rescored and (run_dir / "rescored" / "log.jsonl").exists():
        baseline_log = run_dir / "rescored" / "log.jsonl"
        baseline_source = "prior_rescored"

    suite = QuerySuite.model_validate(yaml.safe_load(queries_path.read_text(encoding="utf-8")))
    specs = {c.id: c for c in suite.conversations}
    gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))

    # Always validate spec when provided; apply it as primary ONLY when policy == "with_specs"
    loaded_spec: LoadedEvalSpec | None = (
        load_eval_spec(spec_path, bundle.name, suite, gold) if spec_path is not None else None
    )
    active_spec: LoadedEvalSpec | None = loaded_spec if policy == "with_specs" else None
    selected_policy = active_spec.policy_name if active_spec is not None else DEFAULT_POLICY

    ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
    biz = ledger["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])

    gold_store, _ = load_gold(bundle)
    xdb = bundle / "extracted.sqlite"
    ext_store = None
    conn = None
    if xdb.exists():
        conn = sqlite3.connect(str(xdb))
        conn.row_factory = sqlite3.Row
        ext_store = Store(conn, biz["business_id"])
    rows = read_log(baseline_log)
    names = sorted({r.configuration for r in rows})
    known = {
        n: c.known
        for n, c in build_configs(bundle, gold_store, ext_store, biz["name"], as_of, names).items()
    }
    if conn is not None:
        conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "log.jsonl").unlink(missing_ok=True)

    scored_primary: list[LogRow] = []
    comp_a_changes: list[dict[str, Any]] = []
    comp_b_changes: list[dict[str, Any]] = []
    policy_reviews: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []

    comp_a_stats: dict[str, dict[str, int]] = {
        n: {
            "turns": 0, "legacy_ok": 0, "strict_ok": 0, "with_specs_ok": 0,
            "primary_ok": 0, "primary_p2f": 0, "primary_f2p": 0, "policy_review": 0,
        }
        for n in names
    }
    comp_b_stats: dict[str, dict[str, int]] = {
        n: {
            "turns": 0, "hist_ok": 0, "primary_ok": 0,
            "parse_recovery": 0, "scorer_p2f": 0, "scorer_f2p": 0,
        }
        for n in names
    }

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
        g_ev = g.get("evidence", []) or []
        g_mn = list(turn.must_not) + list(g.get("must_not", []))

        pp = postprocess(r.raw_response, known[r.configuration], default_as_of=as_of) if r.raw_response else None
        resp = pp.response if pp else None

        legacy_ok, legacy_vals = _legacy_score_turn(resp, turn.expected, g_vals, g_ev, g_mn)
        sc_strict = score_turn(resp, turn.expected, g_vals, g_ev, g_mn)
        g_vals_with_specs = apply_turn_overrides(g_vals, loaded_spec, r.query_id, r.turn_index)
        sc_with_specs = score_turn(resp, turn.expected, g_vals_with_specs, g_ev, g_mn)

        sc_primary = sc_with_specs if active_spec is not None else sc_strict

        sign_only_keys = (
            [k for k, v in g_vals.items() if check_sign_only_mismatch(str(v), resp)]
            if resp is not None
            else []
        )
        needs_policy_review = bool(
            resp is not None
            and not sc_strict.success
            and sign_only_keys
            and sc_strict.answerability_ok
            and not sc_strict.must_not_hits
            and (sc_strict.evidence_recall is None or sc_strict.evidence_recall > 0)
            and all(sc_strict.values.get(k) or (k in sign_only_keys) for k in g_vals)
        )

        notes = (
            [n for n in r.notes.split("; ") if n.startswith("llm_error")]
            + (pp.issues if pp else [])
            + ([f"wording: {w}" for w in pp.wording_flags] if pp else [])
            + [f"must_not_identifier: {p}" for p in sc_primary.must_not_hits if _is_identifier(p)]
            + [f"skipped_must_not: {p}" for p in sc_primary.must_not_skipped]
            + ([f"policy_review:sign_only_debit:{','.join(sign_only_keys)}"] if (needs_policy_review and active_spec is None) else [])
        )
        new_row = r.model_copy(
            update={
                "parsed_ok": resp is not None,
                "success": sc_primary.success,
                "scores": sc_primary.to_dict(),
                "notes": "; ".join(notes),
            }
        )
        write_log([new_row], out_dir / "log.jsonl")
        scored_primary.append(new_row)

        ca = comp_a_stats[r.configuration]
        ca["turns"] += 1
        ca["legacy_ok"] += int(legacy_ok)
        ca["strict_ok"] += int(sc_strict.success)
        ca["with_specs_ok"] += int(sc_with_specs.success)
        ca["primary_ok"] += int(sc_primary.success)
        if legacy_ok and not sc_primary.success:
            ca["primary_p2f"] += 1
        elif (not legacy_ok) and sc_primary.success:
            ca["primary_f2p"] += 1
        if needs_policy_review:
            ca["policy_review"] += 1

        cb = comp_b_stats[r.configuration]
        cb["turns"] += 1
        cb["hist_ok"] += int(bool(r.success))
        cb["primary_ok"] += int(sc_primary.success)
        if (not r.parsed_ok) and (resp is not None) and (not r.success) and sc_primary.success:
            cb["parse_recovery"] += 1
        elif bool(r.success) and not sc_primary.success:
            cb["scorer_p2f"] += 1
        elif (not bool(r.success)) and sc_primary.success:
            cb["scorer_f2p"] += 1

        changed_a_keys = [
            f"{k}={g_vals.get(k)}({legacy_vals.get(k)}->{sc_primary.values.get(k)})"
            for k in sorted(g_vals)
            if legacy_vals.get(k) != sc_primary.values.get(k)
        ]

        rec = {
            "stratum": stratum,
            "run_id": run_dir.name,
            "scenario": r.scenario,
            "baseline_source": baseline_source,
            "configuration": r.configuration,
            "query_id": r.query_id,
            "turn_index": r.turn_index,
            "turn_text": r.turn_text,
            "expected_answerability": turn.expected.value,
            "expected_values": json.dumps(g_vals, sort_keys=True),
            "hist_verdict": bool(r.success),
            "legacy_same_pp_verdict": bool(legacy_ok),
            "v3_1_strict_verdict": bool(sc_strict.success),
            "v3_1_with_specs_verdict": bool(sc_with_specs.success),
            "primary_verdict": bool(sc_primary.success),
            "comp_a_changed": bool(legacy_ok) != bool(sc_primary.success),
            "comp_b_changed": bool(r.success) != bool(sc_primary.success),
            "parse_recovered": (not r.parsed_ok) and (resp is not None),
            "needs_policy_review": needs_policy_review,
            "sign_only_keys": ",".join(sign_only_keys),
            "changed_keys_a": "; ".join(changed_a_keys),
            "raw_response": r.raw_response,
        }
        all_records.append(rec)
        if rec["comp_a_changed"]:
            comp_a_changes.append(rec)
        if rec["comp_b_changed"]:
            comp_b_changes.append(rec)
        if needs_policy_review:
            policy_reviews.append(rec)

    meta_in = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    conv_ids = [q for q in gold if q in specs and q in {r.query_id for r in rows}]
    qlabels = {c.id: list(c.labels) for c in suite.conversations}
    prompt_ver = scored_primary[0].prompt_version if scored_primary else meta_in.get("prompt_version", PROMPT_VERSION)
    write_run_outputs(
        scored_primary,
        out_dir,
        f"{meta_in['run']} ({SCORER_VERSION}:{selected_policy})",
        meta_in["model"],
        meta_in["commit"],
        str(bundle),
        conv_ids,
        len(scored_primary) // len(names),
        prompt_ver,
        query_labels=qlabels,
    )

    metadata = build_run_metadata(
        project_root=PROJECT,
        run_id=f"{meta_in['run']} ({SCORER_VERSION}:{selected_policy})",
        bundle=bundle,
        queries_path=queries_path,
        gold_path=gold_path,
        model_version=meta_in["model"],
        prompt_version=prompt_ver,
        loaded_spec=active_spec,
        rows=scored_primary,
    )
    metadata["hashes"]["rescore_v3_1.py"] = sha256_file(Path(__file__).resolve())
    metadata["stratum"] = stratum
    metadata["original_run_path"] = str(run_dir)
    metadata["baseline_source"] = baseline_source
    metadata["original_code_commit"] = meta_in["commit"]
    metadata["comparison_a_scorer_only"] = comp_a_stats
    metadata["comparison_b_historical_vs_current_pipeline"] = comp_b_stats
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    # Append policy + invariant-subset summary to summary.md
    extra_md = [
        "",
        "## Scoring Policy & Provenance",
        "",
        f"- Scorer version: `{SCORER_VERSION}`",
        f"- Selected primary policy: `{selected_policy}`",
        f"- Metadata & hashes: `metadata.json`",
    ]
    if "invariant_subset_summary" in metadata:
        inv = metadata["invariant_subset_summary"]
        excl = ", ".join(inv["excluded_corpus_sensitive_queries"])
        extra_md += [
            "",
            f"## Predeclared Invariant-Task Subset vs. Corpus-Sensitive Queries (`{excl}`)",
            "",
            f"| Config | All Turns | Invariant Subset (excl. {excl}) | Corpus-Sensitive ({excl}) |",
            "| --- | --- | --- | --- |",
        ]
        for cname, st in inv["per_config"].items():
            a_st, i_st, c_st = st["all_turns"], st["invariant_subset"], st["corpus_sensitive_subset"]
            c_str = f"{c_st['successes']}/{c_st['turns']} ({c_st['rate']:.0%})" if c_st["turns"] else "0/0"
            extra_md.append(
                f"| {cname} | {a_st['successes']}/{a_st['turns']} ({a_st['rate']:.0%}) | "
                f"{i_st['successes']}/{i_st['turns']} ({i_st['rate']:.0%}) | {c_str} |"
            )
    s_md = out_dir / "summary.md"
    s_md.write_text(s_md.read_text(encoding="utf-8") + "\n".join(extra_md) + "\n", encoding="utf-8")

    return {
        "metadata": metadata,
        "comp_a_changes": comp_a_changes,
        "comp_b_changes": comp_b_changes,
        "policy_reviews": policy_reviews,
        "all_records": all_records,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--policy",
        choices=["with_specs", "strict_historical"],
        default="with_specs",
        help="Primary scoring policy to write into logs, CSVs, summaries, and stats inputs.",
    )
    ap.add_argument(
        "--eval-spec",
        type=Path,
        default=DEFAULT_SPEC_PATH,
        help="Versioned evaluation spec YAML (default evaluation/specs_v3_1/amount_semantics_overrides.yaml).",
    )
    ap.add_argument(
        "--out-root",
        type=Path,
        default=None,
        help="Output root directory (default evaluation/results/scorer_v3_1_<policy>).",
    )
    a = ap.parse_args(argv)

    out_root = a.out_root or (PROJECT / "evaluation" / "results" / f"scorer_v3_1_{a.policy}")
    out_root.mkdir(parents=True, exist_ok=True)
    git_head, git_dirty = git_state(REPO_ROOT)

    by_stratum: dict[str, list[dict[str, Any]]] = {}
    all_a_changes: list[dict[str, Any]] = []
    all_b_changes: list[dict[str, Any]] = []
    all_policy_reviews: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []

    for spec in STANDARD_RUNS:
        run_dir = PROJECT / spec.run_rel
        if not (run_dir / "log.jsonl").exists():
            continue
        res = rescore_single_run(
            run_dir=run_dir,
            bundle=PROJECT / spec.bundle_rel,
            queries_path=PROJECT / spec.queries_rel,
            out_dir=out_root / spec.stratum / run_dir.name,
            policy=a.policy,
            spec_path=a.eval_spec,
            stratum=spec.stratum,
            use_prior_rescored=spec.use_prior_rescored,
        )
        by_stratum.setdefault(spec.stratum, []).append(res["metadata"])
        all_a_changes.extend(res["comp_a_changes"])
        all_b_changes.extend(res["comp_b_changes"])
        all_policy_reviews.extend(res["policy_reviews"])
        all_records.extend(res["all_records"])

    # Write Comparison A and Comparison B summaries under out_root
    md_a = [
        f"# Comparison A — Old vs. New Scorer with Identical Postprocessing (`{SCORER_VERSION}`, primary policy: `{a.policy}`)",
        "",
        "Both `legacy_v2_scorer` and `scorer_v3_1` receive the exact same `AssistantResponse` produced by current `postprocess()`.",
        "",
    ]
    for stratum, metas in by_stratum.items():
        tot: dict[str, dict[str, int]] = {}
        for m in metas:
            for cfg, st in m["comparison_a_scorer_only"].items():
                cur = tot.setdefault(cfg, {k: 0 for k in st})
                for k, v in st.items():
                    cur[k] += v
        md_a += [
            f"## Stratum: `{stratum}`",
            "",
            "| Config | Legacy (same pp) | `strict_historical` | `with_specs_v3_1` | Primary Verdict (`" + a.policy + "`) | Primary Delta vs Legacy | Policy Review |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for cfg in sorted(tot):
            c = tot[cfg]
            t = c["turns"] or 1
            md_a.append(
                f"| {cfg} | {c['legacy_ok']}/{c['turns']} ({c['legacy_ok']/t:.1%}) | "
                f"{c['strict_ok']}/{c['turns']} ({c['strict_ok']/t:.1%}) | "
                f"{c['with_specs_ok']}/{c['turns']} ({c['with_specs_ok']/t:.1%}) | "
                f"**{c['primary_ok']}/{c['turns']} ({c['primary_ok']/t:.1%})** | "
                f"{c['primary_ok']-c['legacy_ok']:+d} | {c['policy_review']} |"
            )
        md_a.append("")
    (out_root / "comparison_a_scorer_only.md").write_text("\n".join(md_a) + "\n", encoding="utf-8")

    md_b = [
        f"# Comparison B — Historical Recorded Results vs. Current Pipeline (`{SCORER_VERSION}`, primary policy: `{a.policy}`)",
        "",
        "Not a scorer-only comparison: exact historical `v1` postprocessing cannot be reconstructed from the current tree alone.",
        "",
    ]
    for stratum, metas in by_stratum.items():
        tot: dict[str, dict[str, int]] = {}
        for m in metas:
            for cfg, st in m["comparison_b_historical_vs_current_pipeline"].items():
                cur = tot.setdefault(cfg, {k: 0 for k in st})
                for k, v in st.items():
                    cur[k] += v
        md_b += [
            f"## Stratum: `{stratum}`",
            "",
            "| Config | Historical Recorded | Primary (`" + a.policy + "`) | Net Delta | `postprocess` Parse Recovery | Scorer Rules (P→F / F→P) |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for cfg in sorted(tot):
            c = tot[cfg]
            t = c["turns"] or 1
            md_b.append(
                f"| {cfg} | {c['hist_ok']}/{c['turns']} ({c['hist_ok']/t:.1%}) | "
                f"**{c['primary_ok']}/{c['turns']} ({c['primary_ok']/t:.1%})** | "
                f"{c['primary_ok']-c['hist_ok']:+d} | +{c['parse_recovery']} | {c['scorer_p2f']} / {c['scorer_f2p']} |"
            )
        md_b.append("")
    (out_root / "comparison_b_historical_vs_pipeline.md").write_text("\n".join(md_b) + "\n", encoding="utf-8")

    manifest = {
        "scorer_version": SCORER_VERSION,
        "selected_policy": a.policy,
        "eval_spec": str(a.eval_spec),
        "git_head": git_head,
        "git_dirty": git_dirty,
        "strata": by_stratum,
        "counts": {
            "total_turns": len(all_records),
            "comparison_a_changes": len(all_a_changes),
            "comparison_b_changes": len(all_b_changes),
            "policy_review_cases": len(all_policy_reviews),
        },
    }
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"rescore_v3_1 ({a.policy}) wrote {out_root}: {len(all_records)} turns | "
        f"Comp A changes={len(all_a_changes)} | Comp B changes={len(all_b_changes)} | policy_reviews={len(all_policy_reviews)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
