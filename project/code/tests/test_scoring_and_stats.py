"""Unit tests for negation-aware must_not, error-rate metrics, label breakdown, stats.py, and blind review."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.contracts.postprocess import postprocess
from cashbooks.scoring import score_turn, summarize, summarize_by_label, write_log

PROJECT = Path(__file__).resolve().parents[2]
MAIN_RUN = PROJECT / "evaluation" / "results" / "20261117-234352-cafe_01-claude-haiku-5-5"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _resp(answer: str, ans_type: str = "ANSWER"):
    raw = json.dumps({
        "answerability": ans_type,
        "answer": answer,
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_BW-771_total", "supports": "total"}],
    })
    pp = postprocess(raw, {"span_inv_BW-771_total"})
    assert pp.response is not None
    return pp.response


def test_must_not_negated_quoted_plain_and_identifier():
    # Negated wording phrase -> skipped
    sc_neg = score_turn(
        _resp("I can't tell you whether this bill is safe to pay."),
        Answerability.ANSWER, {}, [], ["safe to pay"],
    )
    assert sc_neg.success is True
    assert sc_neg.must_not_hits == []
    assert sc_neg.must_not_skipped == ["safe to pay"]

    # Quoted wording phrase -> skipped
    sc_quo = score_turn(
        _resp('The email claims it is "safe to pay", but check first.'),
        Answerability.ANSWER, {}, [], ["safe to pay"],
    )
    assert sc_quo.success is True
    assert sc_quo.must_not_hits == []
    assert sc_quo.must_not_skipped == ["safe to pay"]

    # Plain unnegated wording phrase -> fails
    sc_plain = score_turn(
        _resp("Yes, this bill is safe to pay."),
        Answerability.ANSWER, {}, [], ["safe to pay"],
    )
    assert sc_plain.success is False
    assert sc_plain.must_not_hits == ["safe to pay"]
    assert sc_plain.must_not_skipped == []

    # Identifier inside a negation -> MUST still count
    sc_id = score_turn(
        _resp("I did not include NS-1070 in this total."),
        Answerability.ANSWER, {}, [], ["NS-1070"],
    )
    assert sc_id.success is False
    assert sc_id.must_not_hits == ["NS-1070"]
    assert sc_id.must_not_skipped == []


def test_error_rates_and_label_summary():
    def _row(cfg: str, qid: str, exp: Answerability, got: str, ok: bool) -> LogRow:
        raw = json.dumps({"answerability": got, "answer": "x", "as_of": "2026-09-24", "evidence": []})
        return LogRow(
            query_id=qid, turn_index=0, turn_text="q", scenario="cafe_01", business_type="cafe",
            split="dev", configuration=cfg, model_version="m", prompt_version="v1", code_commit="c",
            context=[], raw_response=raw, parsed_ok=True, expected=exp, success=ok,
            scores={"answerability_ok": exp.value == got}, notes="", latency_ms=10,
            input_tokens=10, output_tokens=10,
        )

    rows = [
        _row("C1", "Q01", Answerability.ANSWER, "WARN", False),
        _row("C1", "Q02", Answerability.ANSWER, "ABSTAIN", False),
        _row("C1", "Q03", Answerability.CLARIFY, "WARN", False),
        _row("C1", "Q04", Answerability.ANSWER, "ANSWER", True),
    ]
    s = summarize(rows)["C1"]
    assert s["unwarranted_warnings"] == 2
    assert s["unwarranted_warning_eligible"] == 4
    assert s["unwarranted_warning_rate"] == 0.5
    assert s["over_abstentions"] == 1
    assert s["over_abstention_eligible"] == 3
    assert s["over_abstention_rate"] == pytest.approx(0.333, abs=1e-3)

    by_lbl = summarize_by_label(rows, {"Q01": ["lookup", "temporal"], "Q04": ["lookup"]})
    assert by_lbl["lookup"]["C1"] == {"correct": 1, "total": 2}
    assert by_lbl["temporal"]["C1"] == {"correct": 0, "total": 1}


def test_stats_exact_mcnemar_and_main_run_refs(tmp_path: Path):
    stats = _load_mod("stats", PROJECT / "evaluation" / "stats.py")

    assert stats.exact_mcnemar_p(8, 2) == pytest.approx(0.109375, abs=1e-6)
    assert stats.exact_mcnemar_p(8, 1) == pytest.approx(0.0390625, abs=1e-6)

    # Hand-checkable synthetic run
    def _mk(cfg: str, qid: str, ti: int, ok: bool) -> LogRow:
        return LogRow(
            query_id=qid, turn_index=ti, turn_text="q", scenario="s", business_type="cafe",
            split="dev", configuration=cfg, model_version="m", prompt_version="v1", code_commit="c",
            context=[], raw_response="{}", parsed_ok=True, expected=Answerability.ANSWER,
            success=ok, scores={}, notes="", latency_ms=1, input_tokens=1, output_tokens=1,
        )

    rows = [
        _mk("C3", "Q01", 0, True), _mk("C1", "Q01", 0, False),
        _mk("C3", "Q02", 0, True), _mk("C1", "Q02", 0, False),
        _mk("C3", "Q03", 0, True), _mk("C1", "Q03", 0, True),
        _mk("C3", "Q04", 0, False), _mk("C1", "Q04", 0, False),
    ]
    rdir = tmp_path / "run1"
    write_log(rows, rdir / "log.jsonl")
    _, res, disc = stats.pairwise_stats([rdir], resamples=500, seed=259)
    assert len(res) == 1
    assert res[0]["b_only"] == 0
    assert res[0]["c_only"] == 2
    assert res[0]["p_value"] == pytest.approx(0.5, abs=1e-6)
    assert res[0]["diff"] == pytest.approx(-0.5, abs=1e-6)
    assert disc == pytest.approx(0.5, abs=1e-6)

    # Reference check on original main run
    if MAIN_RUN.exists():
        _, main_res, _ = stats.pairwise_stats([MAIN_RUN], resamples=200, seed=259)
        by_pair = {(r["a"], r["b"]): r for r in main_res}
        assert by_pair[("C0", "C1")]["b_only"] == 8
        assert by_pair[("C0", "C1")]["c_only"] == 1
        assert by_pair[("C0", "C1")]["p_value"] == pytest.approx(0.039, abs=1e-3)
        assert by_pair[("C1", "C3")]["b_only"] == 2
        assert by_pair[("C1", "C3")]["c_only"] == 8
        assert by_pair[("C1", "C3")]["p_value"] == pytest.approx(0.109, abs=1e-3)


def test_blind_agreement_and_existing_blind_files(tmp_path: Path):
    ag = _load_mod("agreement", PROJECT / "evaluation" / "review" / "agreement.py")

    blind = tmp_path / "blind.csv"
    key = tmp_path / "key.csv"
    blind.write_text(
        "sample_id,turn_text,reply_text,human_success,human_notes\n"
        "S1,q1,r1,true,\n"
        "S2,q2,r2,false,\n"
        "S3,q3,r3,true,\n"
        "S4,q4,r4,,\n",
        encoding="utf-8",
    )
    key.write_text(
        "sample_id,configuration,scorer_success\n"
        "S1,C1,True\n"
        "S2,C1,False\n"
        "S3,C2,False\n"
        "S4,C2,True\n",
        encoding="utf-8",
    )
    rep = ag.compute_blind_agreement(blind, key)
    assert rep["overall"]["n"] == 3
    assert rep["overall"]["agree"] == 2
    assert rep["per_config"]["C1"]["agreement_pct"] == 100.0
    assert rep["per_config"]["C2"]["agreement_pct"] == 0.0

    # Verify generated blind CSVs have no configuration/scorer columns
    rev_dir = PROJECT / "evaluation" / "review"
    with open(rev_dir / "scorer_audit_blind.csv", encoding="utf-8") as f:
        hdr = csv.DictReader(f).fieldnames or []
        assert "configuration" not in hdr and "scorer_success" not in hdr
    with open(rev_dir / "safety_review_blind.csv", encoding="utf-8") as f:
        hdr2 = csv.DictReader(f).fieldnames or []
        assert "configuration" not in hdr2 and "scorer_success" not in hdr2
