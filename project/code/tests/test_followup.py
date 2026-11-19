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


def test_session_log_feedback_and_peer_summary(tmp_path: Path, monkeypatch):
    from cashbooks.contracts.evaluation import QuerySuite

    fake_st = types.ModuleType("streamlit")
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    app_mod = _load_module("demo_app_fb", PROJECT / "demo" / "app.py")
    ps_mod = _load_module("peer_summary", PROJECT / "evaluation" / "peer_summary.py")

    sessions_dir = tmp_path / "sessions"
    now = datetime(2026, 11, 18, 19, 0, tzinfo=timezone.utc)

    res1 = ChatTurnResult(
        config_name="C3",
        response=None,
        answerability=Answerability.ANSWER,
        answer="Invoice NS-1048 was paid ($842.00) from account 002299104417.",
        citations=[ResolvedCitation(evidence_id="txn_0119", supports="payment", quote="842.00 USD")],
        latency_ms=250,
    )
    res2 = ChatTurnResult(
        config_name="C3",
        response=None,
        answerability=Answerability.WARN,
        answer="BW-771 remittance account ends in 5507 vs verified 4417.",
        citations=[ResolvedCitation(evidence_id="vh_v_beanworks", supports="verified", quote="****4417")],
        latency_ms=310,
    )

    p_alex = app_mod.log_demo_turn(
        "Alex Rivera",
        "Was NS-1048 paid from account 123456789012?",
        res1,
        sessions_dir=sessions_dir,
        now=now,
        bundle="cafe_01",
    )
    app_mod.update_turn_feedback(p_alex, 0, thumbs="up", comment="Clear citation for 123456789012.")

    app_mod.log_demo_turn(
        "Alex Rivera",
        "Is BW-771 safe to pay to the new bank?",
        res2,
        sessions_dir=sessions_dir,
        now=now,
        bundle="cafe_01",
    )
    app_mod.update_turn_feedback(p_alex, 1, thumbs="down", comment="Wanted shorter warning.")

    p_priya = app_mod.log_demo_turn(
        "Priya Patel",
        "How much credit is applied to NS-1062?",
        res1,
        sessions_dir=sessions_dir,
        now=now,
        bundle="cafe_01",
        thumbs="up",
        comment="Helpful breakdown",
    )

    alex_lines = [json.loads(ln) for ln in p_alex.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(alex_lines) == 2
    rec0 = alex_lines[0]
    for required_key in ("tester", "timestamp", "bundle", "configuration", "question", "reply", "thumbs", "comment"):
        assert required_key in rec0
    assert rec0["tester"] == "Alex Rivera"
    assert rec0["bundle"] == "cafe_01"
    assert rec0["configuration"] == "C3"
    assert rec0["thumbs"] == "up"
    assert "****9012" in rec0["question"]
    assert "****4417" in rec0["reply"]
    assert "****9012" in rec0["comment"]
    assert not re.search(r"\b\d{6,}\b", p_alex.read_text(encoding="utf-8"))
    assert not re.search(r"\b\d{6,}\b", p_priya.read_text(encoding="utf-8"))

    summary_out = tmp_path / "summary.md"
    yaml_out = tmp_path / "peer_queries.yaml"
    tester_rows, suite_payload = ps_mod.write_peer_summary(
        sessions_dir=sessions_dir,
        summary_out=summary_out,
        yaml_out=yaml_out,
    )

    assert len(tester_rows) == 2
    by_name = {r["tester"]: r for r in tester_rows}
    assert by_name["Alex Rivera"]["questions"] == 2
    assert by_name["Alex Rivera"]["thumbs_up"] == 1
    assert by_name["Alex Rivera"]["thumbs_down"] == 1
    assert len(by_name["Alex Rivera"]["comments"]) == 2
    assert by_name["Priya Patel"]["questions"] == 1
    assert by_name["Priya Patel"]["thumbs_up"] == 1
    assert by_name["Priya Patel"]["thumbs_down"] == 0

    md = summary_out.read_text(encoding="utf-8")
    assert "| Alex Rivera | cafe_01 | C3 | 2 | 1 | 1 |" in md
    assert "| Priya Patel | cafe_01 | C3 | 1 | 1 | 0 |" in md
    assert "Wanted shorter warning." in md

    loaded_suite = QuerySuite.model_validate(yaml.safe_load(yaml_out.read_text(encoding="utf-8")))
    assert len(loaded_suite.conversations) == 3
    assert loaded_suite.conversations[0].id == "Q01"
    assert "Was NS-1048 paid" in loaded_suite.conversations[0].turns[0].text
    assert loaded_suite.conversations[1].turns[0].expected == Answerability.WARN
