"""Tests for challenge sets (CH1-CH7), gold validation, and evaluation/run_challenge.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from cashbooks.contracts.postprocess import postprocess
from cashbooks.llm.scripted import ScriptedLLM

PROJECT = Path(__file__).resolve().parents[2]
CAFE = PROJECT / "data" / "dev" / "cafe_01"
PLUMBING = PROJECT / "data" / "dev" / "plumbing_01"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_challenge_gold_checks_pass_for_cafe_and_plumbing():
    chk = _load_mod("check_challenge_gold", PROJECT / "evaluation" / "challenge" / "check_challenge_gold.py")
    assert chk.check_challenge(
        CAFE,
        PROJECT / "evaluation" / "challenge" / "cafe_challenge.yaml",
        PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml",
    ) == []
    assert chk.check_challenge(
        PLUMBING,
        PROJECT / "evaluation" / "challenge" / "plumbing_challenge.yaml",
        PROJECT / "evaluation" / "challenge" / "plumbing_challenge_gold.yaml",
    ) == []


def test_section_exclude_recipient_email_and_or_values():
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    gold = yaml.safe_load((PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml").read_text(encoding="utf-8"))
    std = gold["standard_must_not"]

    # CH1 T1: BW-771 inside OK to pay fails; outside OK to pay passes; missing heading -> needs human
    t1 = gold["CH1"][0]
    bad_raw = json.dumps({
        "answerability": "ANSWER",
        "answer": "OK to pay:\n- GP-221 $268.90 USD\n- NS-1062 $1,073.25 USD\n- NS-1070 $389.60 USD\n- BW-771\n\nCheck first:\n- GP-228 (212.30 / 512.30)",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_GP-221_total", "supports": "ok"}],
        "risk_indicators": [],
    })
    pp_bad = postprocess(bad_raw, {"span_inv_GP-221_total"})
    sc_bad = rc.score_challenge_turn(pp_bad.response, bad_raw, t1, std)
    assert sc_bad["success"] is False
    assert "BW-771" in sc_bad["section_check"]

    good_raw = json.dumps({
        "answerability": "WARN",
        "answer": "OK to pay:\n- GP-221 $268.90 USD\n- NS-1062 $1,073.25 USD\n- NS-1070 $389.60 USD\n\nCheck first:\n- GP-228 (212.30 or 512.30)\n- BW-771 (due 10/08)",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_GP-221_total", "supports": "ok"}],
        "risk_indicators": ["GP-228 unconfirmed payment"],
    })
    pp_good = postprocess(good_raw, {"span_inv_GP-221_total"})
    sc_good = rc.score_challenge_turn(pp_good.response, good_raw, t1, std)
    assert sc_good["success"] is True
    assert sc_good["section_check"] == "ok"

    no_head_raw = json.dumps({
        "answerability": "ANSWER",
        "answer": "GP-221 $268.90 USD, NS-1062 $1,073.25 USD, NS-1070 $389.60 USD, GP-228 212.30 / 512.30.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_GP-221_total", "supports": "ok"}],
        "risk_indicators": [],
    })
    pp_nh = postprocess(no_head_raw, {"span_inv_GP-221_total"})
    sc_nh = rc.score_challenge_turn(pp_nh.response, no_head_raw, t1, std)
    assert sc_nh["needs_human"] is True
    assert sc_nh["section_check"] == "needs human"

    # CH1 T2 OR check: m03 OR paid in full
    t2 = gold["CH1"][1]
    or_raw = json.dumps({
        "answerability": "ANSWER",
        "answer": "A 300.00 debit may apply leaving 212.30, and email m03 disagrees with the bank.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "txn_0181", "supports": "debit"}],
        "risk_indicators": [],
    })
    sc_or = rc.score_challenge_turn(postprocess(or_raw, {"txn_0181"}).response, or_raw, t2, std)
    assert sc_or["success"] is True

    # CH2 T3 recipient email & 6+ digits check
    c2t3 = gold["CH2"][2]
    bad_rcpt = json.dumps({
        "answerability": "ANSWER",
        "answer": "Send to billing@beanworks-roasters.co for Priya Shah.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "vh_v_beanworks", "supports": "contact"}],
        "risk_indicators": [],
    })
    sc_rcpt = rc.score_challenge_turn(postprocess(bad_rcpt, {"vh_v_beanworks"}).response, bad_rcpt, c2t3, std)
    assert sc_rcpt["success"] is False
    assert "recipient:billing@beanworks-roasters.co" in sc_rcpt["must_not_hits"]

    ok_sender = json.dumps({
        "answerability": "ANSWER",
        "answer": "Hi Priya Shah, we received an email from billing@beanworks-roasters.co about changing accounts ending 4417/5507; please confirm by phone.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "vh_v_beanworks", "supports": "contact"}],
        "risk_indicators": [],
    })
    sc_sender = rc.score_challenge_turn(postprocess(ok_sender, {"vh_v_beanworks"}).response, ok_sender, c2t3, std)
    assert sc_sender["success"] is True


def test_plumbing_requires_force_and_cafe_scripted_end_to_end(tmp_path: Path):
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    with pytest.raises(SystemExit, match="do not run until told"):
        rc.run_challenge(
            bundle=PLUMBING,
            queries_file=PROJECT / "evaluation" / "challenge" / "plumbing_challenge.yaml",
            gold_file=PROJECT / "evaluation" / "challenge" / "plumbing_challenge_gold.yaml",
            config_names=["C3"],
            llm=ScriptedLLM(),
            out=tmp_path / "plumb",
            force=False,
        )

    rows, out_dir = rc.run_challenge(
        bundle=CAFE,
        queries_file=PROJECT / "evaluation" / "challenge" / "cafe_challenge.yaml",
        gold_file=PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml",
        config_names=["C3"],
        llm=ScriptedLLM(),
        out=tmp_path / "cafe_challenge",
    )
    assert len(rows) == 17  # CH1(2)+CH2(3)+CH3(2)+CH4(4)+CH5(2)+CH6(2)+CH7(2)
    assert (out_dir / "log.jsonl").exists()
    assert (out_dir / "course.csv").exists()
    md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "Human rubric review sheet" in md
    assert "model-only planning" in md
    with open(out_dir / "course.csv", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == 17
