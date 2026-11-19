"""Offline tests for cashbooks.demo.session using ScriptedLLM."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cashbooks.contracts.common import Answerability
from cashbooks.demo import ChatSession
from cashbooks.llm.scripted import ScriptedLLM

PROJECT = Path(__file__).resolve().parents[2]
CAFE = PROJECT / "data" / "dev" / "cafe_01"
DIGIT_RUN = re.compile(r"\b\d{6,}\b")


def test_two_turn_keeps_history_and_switch_resets():
    replies = {
        "First question": {
            "answerability": "ANSWER",
            "answer": "GP-228 has $212.30 remaining.",
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "span_inv_GP-228_total", "supports": "total"}],
        },
        "Follow-up": {
            "answerability": "ANSWER",
            "answer": "It was due 2026-09-10.",
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "span_inv_GP-228_payment_terms", "supports": "terms"}],
        },
    }
    llm = ScriptedLLM(replies=replies)
    sess = ChatSession(CAFE, "C4", llm)

    r1 = sess.ask("First question")
    assert r1.answerability == Answerability.ANSWER
    assert len(sess.history) == 1
    assert sess.history[0].user == "First question"
    assert sess.history[0].assistant == "GP-228 has $212.30 remaining."

    r2 = sess.ask("Follow-up")
    assert r2.answerability == Answerability.ANSWER
    assert len(sess.history) == 2
    # Second call received the prior turn in its message list
    _, second_msgs = llm.calls[-1]
    assert any(m.role == "model" and "GP-228 has $212.30 remaining." in m.text for m in second_msgs)

    sess.switch_config("C1")
    assert sess.config_name == "C1"
    assert sess.history == []


def test_citations_resolve_to_quotes_for_tools_and_retrieval():
    # C4 tool config: resolves span_*, txn_*, vh_*
    llm_c4 = ScriptedLLM(
        replies={
            "GP-228": {
                "answerability": "ANSWER",
                "answer": "GP-228 has $212.30 remaining.",
                "as_of": "2026-09-24",
                "evidence": [
                    {"evidence_id": "span_inv_GP-228_total", "supports": "invoice total"},
                    {"evidence_id": "txn_0181", "supports": "partial payment"},
                    {"evidence_id": "vh_v_greenway", "supports": "verified vendor"},
                ],
            }
        },
        tool_plan={"GP-228": [("get_bill_status", {"invoice_number": "GP-228", "as_of": "2026-09-24"})]},
    )
    sess_c4 = ChatSession(CAFE, "C4", llm_c4)
    res_c4 = sess_c4.ask("GP-228?")
    assert len(res_c4.citations) == 3
    quotes = {c.evidence_id: c.quote for c in res_c4.citations}
    assert "512.30" in quotes["span_inv_GP-228_total"]
    assert "GREENWAY PRODUCE ACH" in quotes["txn_0181"]
    assert "0456" in quotes["vh_v_greenway"]
    assert not DIGIT_RUN.search(quotes["vh_v_greenway"])
    assert len(res_c4.tool_calls) == 1
    assert res_c4.tool_calls[0].name == "get_bill_status"

    # C1 retrieval config: resolves chunk IDs to chunk text
    llm_c1 = ScriptedLLM(
        replies={
            "GP-228": {
                "answerability": "ANSWER",
                "answer": "GP-228 is $512.30.",
                "as_of": "2026-09-24",
                "evidence": [{"evidence_id": "span_inv_GP-228_p1", "supports": "invoice page"}],
            }
        }
    )
    sess_c1 = ChatSession(CAFE, "C1", llm_c1)
    res_c1 = sess_c1.ask("GP-228?")
    assert len(res_c1.citations) == 1
    assert "GP-228" in res_c1.citations[0].quote
    assert not DIGIT_RUN.search(res_c1.citations[0].quote)
    assert len(res_c1.retrieved_chunks) > 0


def test_12_digit_number_is_masked_in_reply():
    llm = ScriptedLLM(
        replies={
            "account": {
                "answerability": "WARN",
                "answer": "The account is 002299104417.",
                "as_of": "2026-09-24",
                "evidence": [{"evidence_id": "vh_v_beanworks", "supports": "account 002299104417"}],
                "risk_indicators": ["Mismatch with 008812345507"],
                "next_step": "Verify 002299104417 with Priya Shah.",
            }
        }
    )
    sess = ChatSession(CAFE, "C4", llm)
    res = sess.ask("What is the account?")
    assert res.response is not None
    assert "002299104417" not in res.answer
    assert "****4417" in res.answer
    assert not DIGIT_RUN.search(res.answer)
    assert not DIGIT_RUN.search(res.next_step or "")
    assert not DIGIT_RUN.search(res.risk_indicators[0])
    assert not DIGIT_RUN.search(res.citations[0].supports)
    assert not DIGIT_RUN.search(res.citations[0].quote)
