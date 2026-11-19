"""Unit tests for evaluation/retrieval_diagnosis.py using a tiny hand-made log."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.scoring import write_log

PROJECT = Path(__file__).resolve().parents[2]


def _load_rd():
    spec = importlib.util.spec_from_file_location("retrieval_diagnosis", PROJECT / "evaluation" / "retrieval_diagnosis.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["retrieval_diagnosis"] = mod
    spec.loader.exec_module(mod)
    return mod


def _row(
    cfg: str,
    qid: str,
    chunks: list[str],
    success: bool,
    parsed_ok: bool = True,
    ans_ok: bool = True,
    values: dict | None = None,
    must_not: list[str] | None = None,
) -> LogRow:
    return LogRow(
        query_id=qid,
        turn_index=0,
        turn_text=f"Question {qid}",
        scenario="mini",
        business_type="cafe",
        split="dev",
        configuration=cfg,
        model_version="scripted",
        prompt_version="v1",
        code_commit="abc",
        context=[{"chunk_id": c, "source": "s"} for c in chunks],
        raw_response="{}",
        parsed_ok=parsed_ok,
        expected=Answerability.ANSWER,
        success=success,
        scores={
            "answerability_ok": ans_ok,
            "values": values or {},
            "must_not_hits": must_not or [],
        },
        notes="",
        latency_ms=10,
        input_tokens=10,
        output_tokens=10,
    )


def test_retrieval_diagnosis_all_failure_modes_and_rescored(tmp_path: Path):
    rd = _load_rd()
    assert rd.doc_type("inv_NS-1") == "invoice"
    assert rd.doc_type("txn_01") == "bank row"
    assert rd.doc_type("msg_m1") == "message"
    assert rd.doc_type("vh_v1") == "vendor record"
    assert rd.doc_type("cn_1") == "credit note"

    queries = tmp_path / "queries.yaml"
    queries.write_text(yaml.safe_dump({
        "version": "0.1",
        "evaluation_clock": "2026-09-24",
        "status": "draft",
        "conversations": [
            {
                "id": qid,
                "category": "common",
                "scenario": "s",
                "labels": [lbl],
                "turns": [{"text": f"Question {qid}", "expected": "ANSWER", "expected_behavior": "b"}],
            }
            for qid, lbl in [("Q01", "lookup"), ("Q02", "linking"), ("Q03", "temporal"), ("Q04", "comparison"), ("Q05", "dialogue")]
        ],
    }))

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "gold.yaml").write_text(yaml.safe_dump({
        "Q01": [{"values": {"a": "1"}, "evidence": ["inv_A"]}],
        "Q02": [{"values": {"a": "1"}, "evidence": ["inv_A", "txn_01"]}],
        "Q03": [{"values": {"a": "1"}, "evidence": ["inv_B"]}],
        "Q04": [{"values": {"a": "1"}, "evidence": ["inv_C"]}],
        "Q05": [{"values": {"a": "1"}, "evidence": ["inv_D"]}],
    }))

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps({"bundle": str(bundle)}))

    # Original log has Q01 failing; rescored/ has Q01 passing so we verify rescored/ is preferred.
    write_log([_row("C1", "Q01", ["span_inv_A_p1"], success=False, ans_ok=False)], run_dir / "log.jsonl")

    rescored = run_dir / "rescored"
    rescored.mkdir()
    rows = [
        _row("C1", "Q01", ["span_inv_A_p1", "txn_99"], success=True),
        _row("C1", "Q02", ["span_inv_A_p1"], success=False),  # (a) retrieval miss: txn_01
        _row("C1", "Q03", ["span_inv_B_p1"], success=False, ans_ok=False),  # (b) wrong reply type
        _row("C1", "Q04", ["span_inv_C_p1"], success=False, values={"a": False}),  # (c) wrong value
        _row("C1", "Q05", ["span_inv_D_p1"], success=False, parsed_ok=False),  # (d) other (invalid JSON)
        _row("C2", "Q01", ["span_inv_A_total"], success=True),
    ]
    write_log(rows, rescored / "log.jsonl")

    analysis = rd.analyze_run(run_dir, queries_path=queries, bundle_override=bundle)
    assert analysis["source"] == "rescored/log.jsonl"
    by_q = {(t["configuration"], t["query_id"]): t for t in analysis["turns"]}
    assert by_q[("C1", "Q01")]["success"] is True
    assert by_q[("C1", "Q01")]["k"] == 2
    assert by_q[("C1", "Q02")]["recall_at_k"] == pytest.approx(0.5)
    assert by_q[("C1", "Q02")]["failure_category"] == "retrieval miss"
    assert by_q[("C1", "Q03")]["failure_category"] == "evidence retrieved, wrong reply type"
    assert by_q[("C1", "Q04")]["failure_category"] == "evidence retrieved, wrong value"
    assert by_q[("C1", "Q05")]["failure_category"] == "other"

    assert len(analysis["misses"]) == 1
    assert analysis["misses"][0]["doc_id"] == "txn_01"
    assert analysis["misses"][0]["doc_type"] == "bank row"

    md = rd.format_retrieval_md(analysis)
    assert "## Overall mean recall@k and failure breakdown" in md
    assert "## Mean recall@k by question-type label" in md
    assert "txn_01" in md
