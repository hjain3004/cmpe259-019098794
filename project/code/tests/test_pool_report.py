"""Tests for scenario-keyed pooling in stats.py and evaluation/pool_report.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.scoring import write_log

PROJECT = Path(__file__).resolve().parents[2]


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _row(
    config: str,
    scenario: str,
    qid: str,
    turn: int,
    success: bool,
    ans_type: str = "ANSWER",
    expected: Answerability = Answerability.ANSWER,
    recall: float | None = 1.0,
    precision: float | None = 1.0,
) -> LogRow:
    raw = json.dumps({
        "answerability": ans_type,
        "answer": "Reply text.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "txn_0100", "supports": "payment"}],
        "risk_indicators": ["warn"] if ans_type == "WARN" else [],
    })
    return LogRow(
        query_id=qid,
        turn_index=turn,
        turn_text="Question?",
        scenario=scenario,
        business_type="cafe" if scenario == "cafe_01" else "plumbing",
        split="dev",
        configuration=config,
        model_version="scripted",
        prompt_version="answer_system_v1",
        code_commit="test",
        context=[],
        raw_response=raw,
        parsed_ok=True,
        expected=expected,
        success=success,
        scores={
            "parsed": True,
            "answerability_ok": ans_type == expected.value,
            "values": {},
            "evidence_recall": recall,
            "evidence_precision": precision,
            "must_not_hits": [],
            "success": success,
        },
        notes="",
        latency_ms=50,
        input_tokens=20,
        output_tokens=10,
    )


def test_stats_pools_by_scenario_and_repeats(tmp_path: Path):
    stats = _load_mod("stats", PROJECT / "evaluation" / "stats.py")

    r_cafe_1 = tmp_path / "run_cafe_1"
    r_cafe_2 = tmp_path / "run_cafe_2"
    r_plumb = tmp_path / "run_plumb_1"

    # Both scenarios share query_id "Q01". cafe_01 has 2 repeat runs (C1: True, False -> mean 0.5);
    # plumbing_01 has 1 run (C1: True -> 1.0). C0 fails everywhere (0.0).
    # Pooled mean for C1 across the two distinct turns (cafe_01 Q01, plumbing_01 Q01) = (0.5 + 1.0) / 2 = 0.75.
    write_log([_row("C0", "cafe_01", "Q01", 0, False), _row("C1", "cafe_01", "Q01", 0, True)], r_cafe_1 / "log.jsonl")
    write_log([_row("C0", "cafe_01", "Q01", 0, False), _row("C1", "cafe_01", "Q01", 0, False)], r_cafe_2 / "log.jsonl")
    write_log([_row("C0", "plumbing_01", "Q01", 0, False), _row("C1", "plumbing_01", "Q01", 0, True)], r_plumb / "log.jsonl")

    grouping = stats.describe_run_grouping([r_cafe_1, r_cafe_2, r_plumb])
    assert grouping == {
        "cafe_01": ["run_cafe_1", "run_cafe_2"],
        "plumbing_01": ["run_plumb_1"],
    }

    _, res, _ = stats.pairwise_stats([r_cafe_1, r_cafe_2, r_plumb], resamples=200, seed=259)
    assert len(res) == 1
    assert res[0]["a"] == "C0" and res[0]["b"] == "C1"
    assert abs(res[0]["diff"] - (-0.75)) < 1e-9
    # Discordant pairs across the 3 run-turn pairs: C1 wins twice (run_cafe_1, run_plumb_1), 0 ties/losses
    assert res[0]["b_only"] == 0
    assert res[0]["c_only"] == 2


def test_pool_report_prefers_rescored_and_renders_sections(tmp_path: Path):
    pool = _load_mod("pool_report", PROJECT / "evaluation" / "pool_report.py")

    # run1 has a rescored/ folder that flips C0 Q01 from False to True
    run1 = tmp_path / "20261118-0001-cafe_01-claude"
    write_log([_row("C0", "cafe_01", "Q01", 0, False), _row("C1", "cafe_01", "Q01", 0, True)], run1 / "log.jsonl")
    write_log([_row("C0", "cafe_01", "Q01", 0, True), _row("C1", "cafe_01", "Q01", 0, True)], run1 / "rescored" / "log.jsonl")

    run2 = tmp_path / "20261118-0002-cafe_01-claude"
    write_log(
        [
            _row("C0", "cafe_01", "Q01", 0, False, ans_type="WARN", expected=Answerability.ANSWER),
            _row("C1", "cafe_01", "Q01", 0, True),
        ],
        run2 / "log.jsonl",
    )

    run3 = tmp_path / "20261118-0003-plumbing_01-claude"
    write_log(
        [
            _row("C0", "plumbing_01", "Q01", 0, False, ans_type="ABSTAIN", expected=Answerability.ANSWER),
            _row("C1", "plumbing_01", "Q01", 0, True),
        ],
        run3 / "log.jsonl",
    )

    assert pool.resolve_run_dir(run1) == run1 / "rescored"
    assert pool.resolve_run_dir(run2) == run2

    out_dir = tmp_path / "pooled"
    rc = pool.main([str(run1), str(run2), str(run3), "--out", str(out_dir), "--resamples", "100", "--plan", "60", "90", "120"])
    assert rc == 0
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "# Pooled Evaluation Report" in report
    assert "## Turn and conversation success" in report
    assert "## Run-to-run spread" in report
    assert "0%–100%" in report  # C0 cafe_01 spread from rescored run1 (100%) and run2 (0%)
    assert "## Error rates and grounding (pooled)" in report
    assert "## Per-question-type turn success (pooled)" in report
    assert "## Paired statistics" in report
    assert "| 60 |" in report and "| 90 |" in report and "| 120 |" in report
