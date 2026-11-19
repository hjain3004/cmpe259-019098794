"""Tests for answer_system_v2, full-turn history formatting across C0-C4, and postprocess tolerance."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from cashbooks.configs.answer import (
    PROMPT_VERSION,
    Turn,
    _history,
    build_configs,
    format_turn_assistant,
    system_prompt,
)
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.postprocess import postprocess
from cashbooks.llm.scripted import ScriptedLLM
from cashbooks.store.load_gold import load_gold

PROJECT = Path(__file__).resolve().parents[2]
CAFE = PROJECT / "data" / "dev" / "cafe_01"


def test_prompt_v2_and_v1_available():
    assert PROMPT_VERSION == "answer_system_v2"
    v1 = system_prompt("Ember & Oat Cafe", date(2026, 9, 24), tools=False, version="answer_system_v1")
    v2 = system_prompt("Ember & Oat Cafe", date(2026, 9, 24), tools=True)
    assert "next_step" in v2
    assert "Do not ask CLARIFY" in v2
    assert "Do not ask CLARIFY" not in v1


def test_postprocess_drops_unknown_keys_and_abstain_calculation():
    raw_extra = json.dumps({
        "answerability": "ANSWER",
        "answer": "NS-1048 is paid.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "txn_0193", "supports": "payment"}],
        "risk_indicators": [],
        "confidence": 0.99,
        "notes": "extra",
    })
    pp_extra = postprocess(raw_extra, {"txn_0193"})
    assert pp_extra.response is not None
    assert "dropped_unknown_key: confidence" in pp_extra.issues
    assert "dropped_unknown_key: notes" in pp_extra.issues

    raw_abstain_calc = json.dumps({
        "answerability": "ABSTAIN",
        "answer": "I cannot pay NS-1062.",
        "as_of": "2026-09-24",
        "evidence": [],
        "calculation": {
            "steps": ["1118.25 - 45.00"],
            "result": {"amount": "1073.25", "currency": "USD"},
        },
        "risk_indicators": [],
    })
    pp_abs = postprocess(raw_abstain_calc, set())
    assert pp_abs.response is not None
    assert pp_abs.response.answerability is Answerability.ABSTAIN
    assert pp_abs.response.calculation is None
    assert "dropped_abstain_calculation" in pp_abs.issues


def test_format_turn_assistant_and_history_across_c0_to_c4():
    clarify_raw = json.dumps({
        "answerability": "CLARIFY",
        "answer": "There are two Greenway bills.",
        "as_of": "2026-09-24",
        "evidence": [],
        "risk_indicators": [],
        "clarifying_question": "Which one: 1) GP-221 or 2) GP-228?",
        "next_step": "Reply with the invoice number.",
    })
    pp = postprocess(clarify_raw, set())
    assert pp.response is not None
    formatted = format_turn_assistant(pp.response, clarify_raw)
    assert "There are two Greenway bills." in formatted
    assert "Clarifying question: Which one: 1) GP-221 or 2) GP-228?" in formatted
    assert "Next step: Reply with the invoice number." in formatted

    gold_store, _ = load_gold(CAFE)
    import sqlite3
    from cashbooks.store.db import Store

    conn = sqlite3.connect(str(CAFE / "extracted.sqlite"))
    conn.row_factory = sqlite3.Row
    ext_store = Store(conn, "cafe_01")
    cfgs = build_configs(CAFE, gold_store, ext_store, "Ember & Oat Cafe", date(2026, 9, 24), ["C0", "C1", "C2", "C3", "C4"])

    history = [Turn("Did I pay the Greenway bill?", formatted)]
    for cname, cfg in cfgs.items():
        llm = ScriptedLLM()
        cfg.answer(llm, history, "What about the one before that?")
        _, msgs = llm.calls[-1]
        assert msgs[0].text == "Did I pay the Greenway bill?"
        assert "Which one: 1) GP-221 or 2) GP-228?" in msgs[1].text, f"{cname} lost clarifying list"
        assert "What about the one before that?" in msgs[2].text

    # Also verify _history directly
    msgs = _history(history, "The first one.", None)
    assert msgs[1].text == formatted
