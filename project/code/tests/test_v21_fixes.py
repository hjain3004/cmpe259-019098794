"""Tests for v2.1 narrow fixes in match_payments and postprocess."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from cashbooks.contracts.common import Money
from cashbooks.contracts.postprocess import postprocess
from cashbooks.contracts.tools import MatchCandidate, MatchPaymentsResult
from cashbooks.demo.session import ChatSession
from cashbooks.llm.scripted import ScriptedLLM
from cashbooks.store.load_gold import load_gold
from cashbooks.tools.registry import run_tool

CAFE = Path(__file__).resolve().parents[2] / "data" / "dev" / "cafe_01"


@pytest.mark.skipif(not (CAFE / "invoices").exists(), reason="cafe_01 bundle required")
def test_match_payments_unlinked_amount_and_date_returns_candidate_with_amount():
    store, _ = load_gold(CAFE)
    r = json.loads(run_tool(store, "match_payments", {"amount": "1750", "posted_on": "2026-09-18"}))

    assert r["outcome"] == "no_candidates"
    assert len(r["candidates"]) == 1
    cand = r["candidates"][0]
    assert cand["txn_id"] == "txn_0205"
    assert cand["txn_amount"] == {"amount": "-1750.00", "currency": "USD"}
    assert cand["link_status"] == "candidate"
    assert cand["reasons_against"] == ["no bill from a known vendor matches this transaction"]
    assert cand["evidence_ids"] == ["txn_0205"]
    reasons_for_txt = " ".join(cand["reasons_for"])
    assert "2026-09-18" in reasons_for_txt
    assert "descriptor" in reasons_for_txt
    assert "txn_0205" in r["why_undecided"]
    assert "1750.00" in r["why_undecided"]


def test_no_candidates_still_rejects_bill_linked_candidate():
    linked = MatchCandidate(
        bill_id="inv_1",
        invoice_number="NS-1048",
        txn_id="txn_0193",
        txn_amount=Money(amount=Decimal("-842.00"), currency="USD"),
        reasons_for=["test"],
        evidence_ids=["txn_0193"],
    )
    with pytest.raises(ValidationError):
        MatchPaymentsResult(outcome="no_candidates", candidates=[linked])


def test_postprocess_moves_top_level_result_into_calculation_when_missing():
    raw = json.dumps(
        {
            "answerability": "ANSWER",
            "answer": "Remaining balance is $1,073.25 USD.",
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "span_inv_NS-1062_total", "supports": "total"}],
            "calculation": {"steps": ["1118.25 total", "- 45.00 credit"]},
            "result": {"amount": "1073.25", "currency": "USD"},
            "risk_indicators": [],
            "clarifying_question": None,
            "next_step": None,
        }
    )
    pp = postprocess(raw, {"span_inv_NS-1062_total"})
    assert pp.response is not None
    assert pp.response.calculation is not None
    assert pp.response.calculation.result.amount == Decimal("1073.25")
    assert pp.response.calculation.result.currency == "USD"
    assert "moved_result_into_calculation" in pp.issues
    assert "dropped_unknown_key: result" not in pp.issues


def test_postprocess_drops_top_level_result_when_calculation_absent_or_populated():
    raw_no_calc = json.dumps(
        {
            "answerability": "ANSWER",
            "answer": "Invoice NS-1048 was paid.",
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "txn_0193", "supports": "payment"}],
            "calculation": None,
            "result": {"amount": "842.00", "currency": "USD"},
            "risk_indicators": [],
            "clarifying_question": None,
            "next_step": None,
        }
    )
    pp_no_calc = postprocess(raw_no_calc, {"txn_0193"})
    assert pp_no_calc.response is not None
    assert pp_no_calc.response.calculation is None
    assert "dropped_unknown_key: result" in pp_no_calc.issues
    assert "moved_result_into_calculation" not in pp_no_calc.issues

    raw_has_res = json.dumps(
        {
            "answerability": "ANSWER",
            "answer": "Total is $50.00 USD.",
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "txn_0193", "supports": "payment"}],
            "calculation": {
                "steps": ["50.00"],
                "result": {"amount": "50.00", "currency": "USD"},
            },
            "result": {"amount": "99.00", "currency": "USD"},
            "risk_indicators": [],
            "clarifying_question": None,
            "next_step": None,
        }
    )
    pp_has_res = postprocess(raw_has_res, {"txn_0193"})
    assert pp_has_res.response is not None
    assert pp_has_res.response.calculation.result.amount == Decimal("50.00")
    assert "dropped_unknown_key: result" in pp_has_res.issues
    assert "moved_result_into_calculation" not in pp_has_res.issues


@pytest.mark.skipif(
    not ((CAFE / "invoices").exists() and (CAFE / "extracted.sqlite").exists()),
    reason="cafe_01 bundle and extracted.sqlite required",
)
@pytest.mark.parametrize("cfg_name", ["C0", "C1", "C2", "C3", "C4"])
def test_postprocess_move_result_consistent_across_all_configs(cfg_name: str):
    payload = {
        "answerability": "ANSWER",
        "answer": "Remaining is $1,073.25 USD.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "txn_0193", "supports": "payment"}],
        "calculation": {"steps": ["1118.25", "- 45.00"]},
        "result": {"amount": "1073.25", "currency": "USD"},
        "risk_indicators": [],
        "clarifying_question": None,
        "next_step": None,
    }
    sess = ChatSession(CAFE, cfg_name, ScriptedLLM(default=payload))
    res = sess.ask("What is left on NS-1062?")
    assert res.parse_error is None
    assert res.calculation_result == "1073.25 USD"
    assert "moved_result_into_calculation" in res.issues
