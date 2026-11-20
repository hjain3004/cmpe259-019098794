"""Focused offline integration tests for scorer_v3_1 + specs_v3_1 in run_eval.py and rescore_v3_1.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from cashbooks.contracts.evaluation import QuerySuite
from cashbooks.eval_specs import (
    DEFAULT_POLICY,
    EvaluationSpecError,
    apply_turn_overrides,
    load_eval_spec,
)
from cashbooks.llm.scripted import ScriptedLLM
from cashbooks.scoring import SCORER_VERSION, read_log

PROJECT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT / "evaluation" / "specs_v3_1" / "amount_semantics_overrides.yaml"
QUERIES_PATH = PROJECT / "evaluation" / "queries.yaml"
CAFE = PROJECT / "data" / "dev" / "cafe_01"
CAFE_CTRL_X16 = PROJECT / "data" / "dev" / "cafe_01_ctrl_x16"
CAFE_CTRL_X64 = PROJECT / "data" / "dev" / "cafe_01_ctrl_x64"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _suite_and_gold(bundle: Path) -> tuple[QuerySuite, dict]:
    suite = QuerySuite.model_validate(yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8")))
    gold = yaml.safe_load((bundle / "gold.yaml").read_text(encoding="utf-8"))
    return suite, gold


def test_explicit_manifest_maps_controlled_x1_x16_x64_and_rejects_unmapped():
    for bundle in (CAFE, CAFE_CTRL_X16, CAFE_CTRL_X64):
        if not (bundle / "gold.yaml").exists():
            pytest.skip(f"missing bundle {bundle.name}")
        suite, gold = _suite_and_gold(bundle)
        loaded = load_eval_spec(SPEC_PATH, bundle.name, suite, gold)
        assert loaded.resolved_scenario == "cafe_01"
        assert loaded.policy_name == "with_specs_v3_1"
        assert loaded.overrides_by_turn[("Q17", 2)] == {
            "payment": {"kind": "txn_magnitude", "value": "300.00"}
        }
        if bundle.name == "cafe_01":
            assert loaded.corpus_sensitive_queries == {}
        else:
            assert "Q13" in loaded.corpus_sensitive_queries

    # Unmapped suffix must NOT be inferred by loose suffix stripping
    suite, gold = _suite_and_gold(CAFE)
    with pytest.raises(EvaluationSpecError, match="not explicitly mapped"):
        load_eval_spec(SPEC_PATH, "cafe_01_ctrl_x999", suite, gold)


def test_override_validation_rejects_unknown_query_turn_key_kind_and_base_value(tmp_path: Path):
    suite, gold = _suite_and_gold(CAFE)

    def _write_spec(overrides: dict) -> Path:
        p = tmp_path / "bad_spec.yaml"
        p.write_text(
            yaml.safe_dump({
                "version": "test_spec",
                "bundle_to_scenario": {"cafe_01": "cafe_01"},
                "overrides": {"cafe_01": overrides},
            }),
            encoding="utf-8",
        )
        return p

    # 1. Unknown query
    with pytest.raises(EvaluationSpecError, match="unknown query"):
        load_eval_spec(_write_spec({"Q99": {0: {"x": {"kind": "txn_magnitude", "value": "1.00"}}}}), "cafe_01", suite, gold)

    # 2. Out-of-range turn index
    with pytest.raises(EvaluationSpecError, match="out of range"):
        load_eval_spec(_write_spec({"Q17": {9: {"payment": {"kind": "txn_magnitude", "value": "300.00"}}}}), "cafe_01", suite, gold)

    # 3. Unknown value key
    with pytest.raises(EvaluationSpecError, match="unknown value key"):
        load_eval_spec(_write_spec({"Q17": {2: {"nonexistent": {"kind": "txn_magnitude", "value": "300.00"}}}}), "cafe_01", suite, gold)

    # 4. Invalid semantic kind
    with pytest.raises(EvaluationSpecError, match="Invalid amount semantics kind"):
        load_eval_spec(_write_spec({"Q17": {2: {"payment": {"kind": "loose_anything", "value": "300.00"}}}}), "cafe_01", suite, gold)

    # 5. Incompatible base value (must not silently alter gold!)
    with pytest.raises(EvaluationSpecError, match="Incompatible base value"):
        load_eval_spec(_write_spec({"Q17": {2: {"payment": {"kind": "txn_magnitude", "value": "999.00"}}}}), "cafe_01", suite, gold)


def test_runner_and_rescorer_agree_under_both_policies_and_strict_balances_stay_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    run_eval = _load_mod("run_eval_int", PROJECT / "evaluation" / "run_eval.py")
    rescore_v3_1 = _load_mod("rescore_v3_1_int", PROJECT / "evaluation" / "rescore_v3_1.py")

    # Scripted replies:
    # - Q01 t0: balance owed written with WRONG negative sign (-1,073.25 USD) -> MUST FAIL under BOTH policies!
    # - Q17 t0/t1/t2: t2 expresses bank debit txn_0181 as "-300.00 USD" -> FAILS strict_historical, PASSES with_specs_v3_1!
    scripted = ScriptedLLM(
        replies={
            "due in the next 7 days": {
                "answerability": "ANSWER",
                "answer": "NS-1062 is due 2026-10-01 with balance -1,073.25 USD.",
                "as_of": "2026-09-24",
                "evidence": [{"evidence_id": "span_inv_NS-1062_total", "supports": "balance"}],
                "calculation": None,
                "risk_indicators": [],
                "clarifying_question": None,
                "next_step": None,
            },
            "How much do I owe Greenway": {
                "answerability": "CLARIFY",
                "answer": "There are two Greenway bills.",
                "as_of": "2026-09-24",
                "evidence": [],
                "calculation": None,
                "risk_indicators": [],
                "clarifying_question": "Do you mean GP-221 or GP-228?",
                "next_step": None,
            },
            "one before that": {
                "answerability": "ANSWER",
                "answer": "GP-221 is unpaid for $268.90 USD.",
                "as_of": "2026-09-24",
                "evidence": [{"evidence_id": "span_inv_GP-221_total", "supports": "GP-221"}],
                "calculation": None,
                "risk_indicators": [],
                "clarifying_question": None,
                "next_step": None,
            },
            "Show me the payment": {
                "answerability": "ANSWER",
                "answer": "Bank row txn_0181 on 2026-09-09 shows a debit of -300.00 USD.",
                "as_of": "2026-09-24",
                "evidence": [{"evidence_id": "txn_0181", "supports": "debit"}],
                "calculation": None,
                "risk_indicators": [],
                "clarifying_question": None,
                "next_step": None,
            },
        }
    )
    monkeypatch.setattr(run_eval, "make_llm", lambda kind, model: scripted)

    # 1. Legacy/default mode (no --eval-spec -> strict_historical)
    out_strict = tmp_path / "run_strict"
    rc = run_eval.main([
        str(CAFE), "--configs", "C4", "--queries", "Q01", "Q17", "--llm", "scripted", "--out", str(out_strict),
    ])
    assert rc == 0
    strict_rows = {
        (r.query_id, r.turn_index): r for r in read_log(out_strict / "log.jsonl")
    }
    assert strict_rows[("Q01", 0)].success is False  # signed balance rejects negative -1,073.25 USD
    assert strict_rows[("Q17", 2)].success is False  # strict_historical rejects -300.00 USD
    strict_meta = json.loads((out_strict / "metadata.json").read_text(encoding="utf-8"))
    assert strict_meta["scoring_policy"] == DEFAULT_POLICY
    assert strict_meta["scorer_version"] == SCORER_VERSION
    for hkey in ("scoring.py", "postprocess.py", "eval_specs.py", "gold.yaml", "queries.yaml"):
        assert hkey in strict_meta["hashes"]

    # 2. Opt-in with_specs_v3_1 mode (--eval-spec)
    out_specs = tmp_path / "run_with_specs"
    rc2 = run_eval.main([
        str(CAFE), "--configs", "C4", "--queries", "Q01", "Q17", "--llm", "scripted",
        "--eval-spec", str(SPEC_PATH), "--out", str(out_specs),
    ])
    assert rc2 == 0
    specs_rows = {
        (r.query_id, r.turn_index): r for r in read_log(out_specs / "log.jsonl")
    }
    assert specs_rows[("Q01", 0)].success is False  # strict signed balance STILL rejects negative -1,073.25 USD!
    assert specs_rows[("Q17", 2)].success is True   # txn_magnitude accepts -300.00 USD!
    specs_meta = json.loads((out_specs / "metadata.json").read_text(encoding="utf-8"))
    assert specs_meta["scoring_policy"] == "with_specs_v3_1"
    assert "eval_spec" in specs_meta["hashes"] and "eval_spec_manifest" in specs_meta["hashes"]

    # Verify log.jsonl, course.csv, summary.json, and summary.md agree on primary verdict
    sum_json = json.loads((out_specs / "summary.json").read_text(encoding="utf-8"))
    assert sum_json["configs"]["C4"]["successes"] == sum(1 for r in specs_rows.values() if r.success)
    with open(out_specs / "course.csv", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert sum(1 for r in csv_rows if r["success"] == "True") == sum_json["configs"]["C4"]["successes"]
    assert "with_specs_v3_1" in (out_specs / "summary.md").read_text(encoding="utf-8")

    # 3. Rescore the exact saved run_strict log under BOTH policies and prove 100% runner == rescorer parity!
    re_strict = tmp_path / "rescore_strict"
    rescore_v3_1.rescore_single_run(
        run_dir=out_strict, bundle=CAFE, queries_path=QUERIES_PATH,
        out_dir=re_strict, policy="strict_historical", spec_path=SPEC_PATH,
    )
    re_strict_rows = {(r.query_id, r.turn_index): r.success for r in read_log(re_strict / "log.jsonl")}
    assert re_strict_rows == {k: v.success for k, v in strict_rows.items()}

    re_specs = tmp_path / "rescore_with_specs"
    rescore_v3_1.rescore_single_run(
        run_dir=out_strict, bundle=CAFE, queries_path=QUERIES_PATH,
        out_dir=re_specs, policy="with_specs", spec_path=SPEC_PATH,
    )
    re_specs_rows = {(r.query_id, r.turn_index): r.success for r in read_log(re_specs / "log.jsonl")}
    assert re_specs_rows == {k: v.success for k, v in specs_rows.items()}
    re_sum = json.loads((re_specs / "summary.json").read_text(encoding="utf-8"))
    assert re_sum["configs"]["C4"]["successes"] == sum(1 for v in re_specs_rows.values() if v)


@pytest.mark.skipif(not (CAFE_CTRL_X16 / "gold.yaml").exists(), reason="cafe_01_ctrl_x16 required")
def test_controlled_scaling_bundle_reports_predeclared_q13_split(tmp_path: Path):
    run_eval = _load_mod("run_eval_scale_int", PROJECT / "evaluation" / "run_eval.py")
    out_dir = tmp_path / "ctrl_x16_dryrun"
    rc = run_eval.main([
        str(CAFE_CTRL_X16), "--configs", "C4", "--llm", "scripted",
        "--eval-spec", str(SPEC_PATH), "--out", str(out_dir),
    ])
    assert rc == 0
    meta = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["resolved_scenario"] == "cafe_01"
    assert meta["scoring_policy"] == "with_specs_v3_1"
    inv = meta["invariant_subset_summary"]["per_config"]["C4"]
    assert inv["all_turns"]["turns"] == 28
    assert inv["invariant_subset"]["turns"] == 27
    assert inv["corpus_sensitive_subset"]["turns"] == 1
    assert "Predeclared Invariant-Task Subset" in (out_dir / "summary.md").read_text(encoding="utf-8")
