"""Offline tests for warning calibration, structured dialogue state, and postprocess reliability."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from cashbooks.configs.answer import Turn, build_configs, format_turn_assistant, system_prompt
from cashbooks.configs.dialogue_state import (
    DialogueState,
    derive_dialogue_state,
    format_state_block,
    resolve_reference,
    retrieval_query_terms,
    update_dialogue_state,
)
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.postprocess import postprocess
from cashbooks.contracts.tools import TOOLS_BY_NAME
from cashbooks.demo.session import ChatSession
from cashbooks.llm.scripted import ScriptedLLM
from cashbooks.store.db import Store
from cashbooks.store.load_gold import load_gold
from cashbooks.tools.registry import run_tool

CAFE = Path(__file__).resolve().parents[2] / "data" / "dev" / "cafe_01"
PLUMBING = Path(__file__).resolve().parents[2] / "data" / "dev" / "plumbing_01"
HAS_CAFE = (CAFE / "invoices").exists() and (CAFE / "extracted.sqlite").exists()
HAS_PLUMBING = (PLUMBING / "invoices").exists()


# ---------------------------------------------------------------------------
# DialogueState unit tests (strictly from displayed turns)
# ---------------------------------------------------------------------------


def test_dialogue_state_ordinal_and_relative_chain():
    t0 = Turn(
        user="Which bills are overdue as of today?",
        assistant=(
            "Two invoices are overdue:\n"
            "1. GP-221 (GreenPlate Produce): $268.90 USD, due 2026-09-05.\n"
            "2. GP-228 (GreenPlate Produce): $512.30 USD, due 2026-09-10.\n"
            "3. BW-771 (BeanWorks Supply): $1200.00 USD, due 2026-09-18.\n"
            "Next step: Verify BW-771 bank-change note before paying BW-999."
        ),
    )
    st0 = derive_dialogue_state([t0])
    assert st0.displayed_invoices == ["GP-221", "GP-228", "BW-771"]
    assert "BW-999" not in st0.displayed_invoices
    assert st0.status_filter == "overdue"
    assert st0.date_filter == "today"
    assert st0.selected_invoice is None

    # Turn 1: ordinal picks GP-228 cleanly
    res1 = resolve_reference(st0, "What is the status of the second one?")
    assert res1.resolved_invoice == "GP-228"
    assert res1.ambiguous_reason is None

    t1 = Turn(
        user="What is the status of the second one?",
        assistant="GP-228 is partly paid with $212.30 USD remaining if candidate payment applies.",
    )
    st1 = derive_dialogue_state([t0, t1])
    # Single-item follow-up inside the displayed list retains list order for relative navigation
    assert st1.displayed_invoices == ["GP-221", "GP-228", "BW-771"]
    assert st1.selected_invoice == "GP-228"

    # Turn 2: "the one before that" resolves deterministically to GP-221
    res2 = resolve_reference(st1, "What about the one before that?")
    assert res2.resolved_invoice == "GP-221"
    assert res2.ambiguous_reason is None


def test_dialogue_state_ambiguity_not_guessed_and_descriptor_clarifies():
    st = update_dialogue_state(
        DialogueState(),
        "Which bills are open?",
        "Open bills:\n1. NS-1048 (Northside Roasters)\n2. BW-771 (BeanWorks Supply)\nNext step: None.",
    )
    # Bare pronoun with 2 displayed bills and no prior selection must stay ambiguous
    amb = resolve_reference(st, "Should I pay it today?")
    assert amb.resolved_invoice is None
    assert amb.ambiguous_reason is not None
    assert "NS-1048" in amb.ambiguous_reason and "BW-771" in amb.ambiguous_reason

    # Out-of-range ordinal stays ambiguous
    oor = resolve_reference(st, "Tell me about the fourth one")
    assert oor.resolved_invoice is None
    assert oor.ambiguous_reason is not None

    # Descriptor phrase disambiguates from displayed snippets
    desc = resolve_reference(st, "The BeanWorks one.")
    assert desc.resolved_invoice == "BW-771"
    assert desc.ambiguous_reason is None

    # Clarification question with options parses candidates
    st_clar = update_dialogue_state(
        DialogueState(),
        "How much did we spend with them?",
        "I need one detail first.\nClarifying question: Which vendor do you mean: Northside Roasters or BeanWorks Supply?",
    )
    assert st_clar.clarifying_options == ["Northside Roasters", "BeanWorks Supply"]
    res_opt = resolve_reference(st_clar, "Northside Roasters")
    assert res_opt.resolved_vendor == "Northside Roasters"


def test_dialogue_state_topic_shift_resets_stale_selection():
    t0 = Turn(user="Check invoice GP-221 as of 2026-09-24 in USD", assistant="GP-221 owes $268.90 USD.")
    st0 = derive_dialogue_state([t0])
    assert st0.selected_invoice == "GP-221"
    assert st0.currency_filter == "USD"
    assert st0.date_filter == "2026-09-24"

    t1 = Turn(
        user="Summarize our coffee purchases in August 2026.",
        assistant="Purchases totaled $486.00 USD across 12 bags.",
    )
    st1 = derive_dialogue_state([t0, t1])
    assert st1.selected_invoice is None
    assert st1.displayed_invoices == []
    assert st1.date_filter == "August 2026"

    # Following turn saying "it" now has no invoice referent -> must stay ambiguous
    res = resolve_reference(st1, "Is it overdue?")
    assert res.resolved_invoice is None
    assert res.ambiguous_reason is not None


def test_retrieval_query_terms_only_expand_justified_references():
    st = update_dialogue_state(
        DialogueState(),
        "List open bills",
        "1. GP-221 (GreenPlate Produce)\n2. GP-228 (GreenPlate Produce)",
    )
    expanded = retrieval_query_terms(st, "What is the status of the second one?")
    assert "GP-228" in expanded

    # Ambiguous pronoun must NOT fabricate an invoice ID for BM25
    unexpanded = retrieval_query_terms(st, "Should I pay it today?")
    assert unexpanded == "Should I pay it today?"


# ---------------------------------------------------------------------------
# Cross-config C0-C4 & ChatSession consistency with ScriptedLLM
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_CAFE, reason="cafe_01 rendered bundle + extracted.sqlite required")
def test_c0_through_c4_share_dialogue_state_and_c1_c2_retrieve_resolved_target():
    ledger = json.loads((CAFE / "ledger.json").read_text())
    biz = ledger["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])
    gold_store, _ = load_gold(CAFE)
    conn = sqlite3.connect(str(CAFE / "extracted.sqlite"))
    conn.row_factory = sqlite3.Row
    ext_store = Store(conn, biz["business_id"])
    configs = build_configs(CAFE, gold_store, ext_store, biz["name"], as_of, ["C0", "C1", "C2", "C3", "C4"])

    history = [
        Turn(
            user="Which bills are overdue right now?",
            assistant="Overdue invoices:\n1. GP-221 ($268.90 USD)\n2. GP-228 ($512.30 USD)",
        )
    ]

    for cname, cfg in configs.items():
        llm = ScriptedLLM(
            replies={
                "the second one": {
                    "answerability": "ANSWER",
                    "answer": "GP-228 is overdue.",
                    "as_of": "2026-09-24",
                    "evidence": [{"evidence_id": "span_inv_GP-228_p1", "supports": "GP-228"}],
                    "calculation": None,
                    "risk_indicators": [],
                    "clarifying_question": None,
                    "next_step": None,
                }
            }
        )
        out = cfg.answer(llm, history, "What is the status of the second one?")
        last_user_prompt = llm.calls[0][1][-1].text
        assert "CONVERSATION STATE" in last_user_prompt, f"{cname} missing state block"
        assert "1) GP-221, 2) GP-228" in last_user_prompt
        assert "Resolved reference in current question: invoice GP-228" in last_user_prompt
        if cname in ("C1", "C2"):
            retrieved_ids = [c["chunk_id"] for c in out.context]
            assert any("GP-228" in cid for cid in retrieved_ids), f"{cname} failed to retrieve GP-228: {retrieved_ids}"

        # Verify ambiguous pronoun sends explicit CLARIFY instruction without guessing
        amb_llm = ScriptedLLM()
        amb_out = cfg.answer(amb_llm, history, "Should I pay it today?")
        amb_prompt = amb_llm.calls[0][1][-1].text
        assert "Unresolved ambiguity:" in amb_prompt and "CLARIFY" in amb_prompt
        if cname in ("C1", "C2"):
            assert len(amb_out.context) > 0


@pytest.mark.skipif(not HAS_CAFE or not HAS_PLUMBING, reason="cafe_01 and plumbing_01 bundles required")
def test_chat_session_dialogue_state_and_session_isolation():
    replies = {
        "Which bills": {
            "answerability": "ANSWER",
            "answer": "Open: 1. GP-221 ($268.90 USD), 2. GP-228 ($512.30 USD).",
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "span_inv_GP-221_p1", "supports": "GP-221"}],
            "calculation": None,
            "risk_indicators": [],
            "clarifying_question": None,
            "next_step": None,
        },
        "the second one": {
            "answerability": "ANSWER",
            "answer": "GP-228 has a candidate payment of $300.00 USD.",
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "span_inv_GP-228_p1", "supports": "GP-228"}],
            "calculation": None,
            "risk_indicators": [],
            "clarifying_question": None,
            "next_step": None,
        },
    }
    cafe_sess = ChatSession(CAFE, "C4", ScriptedLLM(replies=replies))
    plumb_sess = ChatSession(PLUMBING, "C4", ScriptedLLM())

    cafe_sess.ask("Which bills are overdue?")
    assert cafe_sess.dialogue_state.displayed_invoices == ["GP-221", "GP-228"]
    assert plumb_sess.dialogue_state.displayed_invoices == []

    cafe_sess.ask("Tell me about the second one.")
    assert cafe_sess.dialogue_state.selected_invoice == "GP-228"
    assert cafe_sess.dialogue_state.displayed_invoices == ["GP-221", "GP-228"]

    cafe_sess.reset()
    assert cafe_sess.dialogue_state.turn_count == 0
    assert cafe_sess.dialogue_state.displayed_invoices == []
    assert cafe_sess.dialogue_state.selected_invoice is None


# ---------------------------------------------------------------------------
# Postprocess reliability & logging tests
# ---------------------------------------------------------------------------


def test_postprocess_normalizations_masking_and_logs():
    # 1. Omitted as_of filled when default_as_of is given, fails without default_as_of
    raw_no_date = json.dumps(
        {
            "answerability": "ANSWER",
            "answer": "Account 008812345507 owes $500.00 USD.",
            "evidence": [{"evidence_id": "txn_0193", "supports": "payment 008812345507"}],
            "calculation": {"steps": ["500.00 from 008812345507"], "result": {"amount": "500.00", "currency": "USD"}},
            "risk_indicators": [],
            "clarifying_question": "",
            "next_step": "   ",
        }
    )
    assert postprocess(raw_no_date, {"txn_0193"}).response is None
    pp = postprocess(raw_no_date, {"txn_0193"}, default_as_of=date(2026, 9, 24))
    assert pp.response is not None
    assert pp.response.as_of == date(2026, 9, 24)
    assert pp.response.clarifying_question is None
    assert pp.response.next_step is None
    assert "****5507" in pp.response.answer
    assert "008812345507" not in pp.response.answer
    assert "008812345507" not in pp.response.evidence[0].supports
    assert "008812345507" not in pp.response.calculation.steps[0]
    assert "filled_missing_as_of" in pp.issues
    assert "normalized_empty_clarifying_question" in pp.issues
    assert "normalized_empty_next_step" in pp.issues
    assert "masked_number_in_answer" in pp.issues
    assert "masked_number_in_calculation" in pp.issues
    assert "masked_number_in_evidence" in pp.issues

    # 2. CLARIFY calculation dropped + null lists normalized + risk_indicators masked
    raw_clarify = json.dumps(
        {
            "answerability": "CLARIFY",
            "answer": "Please confirm which bill.",
            "as_of": "2026-09-24",
            "evidence": None,
            "calculation": {"steps": ["100.00"], "result": {"amount": "100.00", "currency": "USD"}},
            "risk_indicators": None,
            "clarifying_question": "Which bill: NS-1031 or NS-1048?",
            "next_step": None,
        }
    )
    pp_clar = postprocess(raw_clarify, set())
    assert pp_clar.response is not None
    assert pp_clar.response.answerability == Answerability.CLARIFY
    assert pp_clar.response.calculation is None
    assert pp_clar.response.evidence == []
    assert pp_clar.response.risk_indicators == []
    assert "dropped_clarify_calculation" in pp_clar.issues
    assert "normalized_null_evidence" in pp_clar.issues
    assert "normalized_null_risk_indicators" in pp_clar.issues

    raw_warn_digits = json.dumps(
        {
            "answerability": "WARN",
            "answer": "Do not remit without checking.",
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "vh_v_beanworks", "supports": "remit change"}],
            "calculation": None,
            "risk_indicators": ["Requested account 008812345507 differs from 112233449911"],
            "clarifying_question": None,
            "next_step": "Call vendor on file.",
        }
    )
    pp_warn = postprocess(raw_warn_digits, {"vh_v_beanworks"})
    assert pp_warn.response is not None
    assert "008812345507" not in pp_warn.response.risk_indicators[0]
    assert "****5507" in pp_warn.response.risk_indicators[0]
    assert "****9911" in pp_warn.response.risk_indicators[0]
    assert "masked_number_in_risk_indicators" in pp_warn.issues


# ---------------------------------------------------------------------------
# Warning calibration prompt + neutral tool outputs preserve risk fields
# ---------------------------------------------------------------------------


def test_prompt_and_tools_warning_calibration():
    sys_no_tools = system_prompt("Test Biz", date(2026, 9, 24), tools=False)
    sys_tools = system_prompt("Test Biz", date(2026, 9, 24), tools=True)
    for prompt in (sys_no_tools, sys_tools):
        assert "ANSWER with background caution" in prompt
        assert "Routine query + unrelated risky note -> ANSWER" in prompt
        assert "Payment/safety query + discrepancy -> WARN" in prompt
        assert "under 1,200 characters" in prompt

    list_desc = TOOLS_BY_NAME["list_open_bills"].description.lower()
    bill_desc = TOOLS_BY_NAME["get_bill_status"].description.lower()
    assert "recommend verifying" not in list_desc
    assert "always mention" not in bill_desc
    assert "has_note_outside_remit_fields" in list_desc
    assert "has_note_outside_remit_fields" in bill_desc


@pytest.mark.skipif(not HAS_CAFE, reason="cafe_01 rendered bundle required")
def test_tools_still_preserve_risk_evidence_without_prescriptive_bias():
    gold_store, _ = load_gold(CAFE)
    status = json.loads(run_tool(gold_store, "get_bill_status", {"invoice_number": "BW-771", "as_of": "2026-09-24"}))
    assert status["has_note_outside_remit_fields"] is True
    assert status["memo"] is not None
    cmp_res = json.loads(run_tool(gold_store, "compare_vendor_payment_details", {"invoice_number": "BW-771"}))
    assert cmp_res["outcome"] == "changed"
