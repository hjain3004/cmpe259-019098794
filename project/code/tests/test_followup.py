"""Tests for grounding/usability metrics, scorer audit sampling/reporting, and peer-testing tools."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import yaml

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.demo.session import ChatTurnResult, ResolvedCitation
from cashbooks.scoring import summarize, write_run_outputs

PROJECT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_row(config: str, qid: str, answer: str, cites: list[str], recall: float | None, precision: float | None,
              success: bool = True) -> LogRow:
    raw = json.dumps({
        "answerability": "ANSWER",
        "answer": answer,
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": cid, "supports": "claim"} for cid in cites],
        "risk_indicators": [],
    })
    return LogRow(
        query_id=qid,
        turn_index=0,
        turn_text="Question?",
        scenario="cafe_01",
        business_type="cafe",
        split="dev",
        configuration=config,
        model_version="scripted",
        prompt_version="answer_system_v1",
        code_commit="test",
        context=[],
        raw_response=raw,
        parsed_ok=True,
        expected=Answerability.ANSWER,
        success=success,
        scores={
            "parsed": True,
            "answerability_ok": True,
            "values": {},
            "evidence_recall": recall,
            "evidence_precision": precision,
            "must_not_hits": [],
            "success": success,
        },
        notes="",
        latency_ms=100,
        input_tokens=50,
        output_tokens=20,
    )


def test_grounding_and_usability_metrics(tmp_path: Path):
    short_10 = " ".join(["word"] * 10)
    med_50 = " ".join(["word"] * 50)
    long_130 = " ".join(["word"] * 130)

    rows = [
        _make_row("C1", "Q01", short_10, ["txn_1"], 1.0, 0.5),
        _make_row("C1", "Q02", med_50, ["txn_1", "txn_2", "txn_3"], 0.5, 0.5),
        _make_row("C1", "Q03", long_130, ["txn_1", "txn_2"], None, None),
    ]
    summary = summarize(rows)["C1"]
    assert summary["mean_evidence_recall"] == 0.75
    assert summary["mean_evidence_precision"] == 0.5
    assert summary["mean_citations"] == 2.0
    assert summary["median_words"] == 50
    assert summary["p90_words"] == 130
    assert summary["under_120_words_share"] == round(2 / 3, 3)

    lines = write_run_outputs(rows, tmp_path, "r1", "scripted", "abc", "cafe_01", ["Q01", "Q02", "Q03"], 3, "v1")
    md = "\n".join(lines)
    assert "## Grounding and usability" in md
    assert "| C1 | 0.750 | 0.500 | 2.00 | 50 | 130 | 67% |" in md


def test_audit_sample_and_report(tmp_path: Path):
    audit = _load_module("audit_sample", PROJECT / "evaluation" / "audit_sample.py")
    run_dir = PROJECT / "evaluation" / "results" / "20261117-154644-cafe_01-claude-haiku-5-5"
    out_csv = tmp_path / "scorer_audit.csv"

    recs = audit.write_audit_csv(run_dir, out_csv=out_csv, n=40, seed=42)
    assert len(recs) == 40
    assert out_csv.exists()

    with open(out_csv, encoding="utf-8") as f:
        loaded = list(csv.DictReader(f))
    assert len(loaded) == 40
    assert all(r["human_success"] == "" for r in loaded)
    assert all(not re.search(r"\b\d{6,}\b", r["reply"]) for r in loaded)
    assert all(not re.search(r"\b\d{6,}\b", r["automatic_reasons"]) for r in loaded)

    # Balance check: 10 per config, ~half pass / half fail
    by_cfg = {}
    for r in loaded:
        by_cfg.setdefault(r["config"], []).append(r["automatic_success"] == "True")
    assert set(by_cfg.keys()) == {"C1", "C2", "C3", "C4"}
    assert all(len(v) == 10 for v in by_cfg.values())

    # Fill human_success with 2 disagreements and test report mode
    filled_csv = tmp_path / "filled.csv"
    disagree_count = 0
    for i, r in enumerate(loaded):
        auto = r["automatic_success"] == "True"
        if i in (0, 1):
            r["human_success"] = str(not auto)
            r["human_note"] = "test disagreement"
            disagree_count += 1
        else:
            r["human_success"] = str(auto)
    with open(filled_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=audit.CSV_FIELDS)
        w.writeheader()
        w.writerows(loaded)

    rep = audit.compute_agreement(filled_csv)
    assert rep["overall"]["n"] == 40
    assert rep["overall"]["agree"] == 38
    assert rep["overall"]["agreement_pct"] == 95.0
    assert 0.85 < rep["overall"]["kappa"] < 1.0
    assert len(rep["disagreements"]) == disagree_count
    text = audit.format_agreement_report(rep)
    assert "Cohen's kappa" in text
    assert "Disagreements (2):" in text


def test_demo_logging_and_peer_queries(tmp_path: Path, monkeypatch):
    # Stub streamlit so demo/app.py imports cleanly in headless pytest
    fake_st = types.ModuleType("streamlit")
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    app_mod = _load_module("demo_app", PROJECT / "demo" / "app.py")
    pq_mod = _load_module("peer_queries", PROJECT / "evaluation" / "peer_queries.py")

    sessions_dir = tmp_path / "sessions"
    res = ChatTurnResult(
        config_name="C3",
        response=None,
        answerability=Answerability.ANSWER,
        answer="Account ends in 002299104417.",
        citations=[ResolvedCitation(evidence_id="vh_v_beanworks", supports="account", quote="****4417")],
        latency_ms=320,
    )
    now = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)
    log_path = app_mod.log_demo_turn("Alex Rivera", "What is BeanWorks' bank?", res, sessions_dir=sessions_dir, now=now)
    # Second turn: duplicate question + known question from queries.yaml
    app_mod.log_demo_turn("Alex Rivera", "What is BeanWorks' bank?", res, sessions_dir=sessions_dir, now=now)
    app_mod.log_demo_turn("Alex Rivera", "Did I already pay invoice NS-1048?", res, sessions_dir=sessions_dir, now=now)

    assert log_path.name == "2026-11-17-alex-rivera.jsonl"
    raw_log = log_path.read_text(encoding="utf-8")
    assert not re.search(r"\b\d{6,}\b", raw_log)
    assert "****4417" in raw_log

    out_yaml = tmp_path / "peer_queries_draft.yaml"
    drafts = pq_mod.write_peer_queries_draft(sessions_dir=sessions_dir, out_path=out_yaml)
    assert len(drafts) == 1
    assert drafts[0]["question"] == "What is BeanWorks' bank?"
    loaded = yaml.safe_load(out_yaml.read_text(encoding="utf-8"))
    assert loaded["count"] == 1
