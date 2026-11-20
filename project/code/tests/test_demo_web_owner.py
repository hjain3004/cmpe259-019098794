"""Tests for the owner-first demo UI helpers, attention cards, badges, and boundaries."""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from cashbooks.attention import find_attention_items
from cashbooks.contracts.common import Answerability, PaymentState
from cashbooks.demo.session import ChatTurnResult, ResolvedCitation, ToolTrace
from cashbooks.demo.web import (
    CONFIGS,
    PROJECT,
    QUESTIONS,
    RESPONSE_BADGES,
    bill_status_badge,
    format_date_owner,
    format_header_date,
    format_money_owner,
    make_server,
    present_result,
    DemoService,
)

_LEAK_RE = re.compile(
    r"(?:\b(?:span|vh|msg)_[A-Za-z0-9_-]+\b|\btxn_\d+\b|"
    r"\b(?:list_open_bills|get_bill_status|match_payments|sum_amount_due|"
    r"compare_vendor_payment_details|summarize_purchases|get_source_evidence)\b|\{)"
)
_ALLOWED_STATUSES = {"Paid", "Partly paid?", "Unpaid", "Overdue", "Check before paying"}


def test_status_and_response_badge_mapping():
    assert RESPONSE_BADGES["WARN"] == "Heads up"
    assert RESPONSE_BADGES["CLARIFY"] == "I need one detail"
    assert RESPONSE_BADGES["ABSTAIN"] == "I can't tell from your records"
    assert RESPONSE_BADGES["ANSWER"] == ""

    assert bill_status_badge(PaymentState.PAID) == "Paid"
    assert bill_status_badge(PaymentState.OVERPAID) == "Paid"
    assert bill_status_badge(PaymentState.PARTIAL) == "Partly paid?"
    assert bill_status_badge(PaymentState.UNPAID, overdue=False) == "Unpaid"
    assert bill_status_badge(PaymentState.UNPAID, overdue=True) == "Overdue"
    assert bill_status_badge(PaymentState.UNPAID, needs_check=True) == "Check before paying"

    assert format_money_owner("1073.25", "USD") == "$1,073.25"
    assert format_date_owner("2026-10-01") == "Oct 1"
    assert format_header_date("2026-09-24") == "24 Sep 2026"

    for kind, expected_badge in RESPONSE_BADGES.items():
        if kind == "ERROR":
            res = ChatTurnResult(config_name="C3", response=None, parse_error="err")
        else:
            res = ChatTurnResult(
                config_name="C3",
                response=object(),
                answerability=Answerability(kind),
                answer="Sample text.",
            )
        assert present_result(res, "rehearsal")["badge"] == expected_badge


@pytest.mark.skipif(
    not (PROJECT / "data/dev/cafe_01/extracted.sqlite").is_file(),
    reason="cafe_01 extracted.sqlite required",
)
def test_attention_panel_matches_attention_py_and_hides_ids_in_owner_fields():
    svc = DemoService(mode="rehearsal")
    meta = svc.metadata()
    assert meta["business"] == "Ember & Oat Cafe"
    assert meta["as_of"] == "2026-09-24"
    assert meta["as_of_display"] == "24 Sep 2026"

    groups = meta["attention"]
    assert [g["title"] for g in groups] == ["Overdue", "Due soon", "Check before paying", "Possible money back"]

    by_title = {g["title"]: g["cards"] for g in groups}
    assert {c["invoice"] for c in by_title["Overdue"]} == {"GP-221", "GP-228"}
    assert {c["invoice"] for c in by_title["Due soon"]} == {"NS-1062"}
    assert {c["invoice"] for c in by_title["Check before paying"]} == {"BW-771", "GP-228"}
    assert {c["invoice"] for c in by_title["Possible money back"]} == {"NS-1031"}

    # Confirm attention.py was used as underlying source (all grouped invoices appear in attention_items / open bills)
    ext_store, gold_store, _ = svc._stores_for_session(None)
    raw_items = find_attention_items(ext_store or gold_store, date(2026, 9, 24))
    raw_subjects = {it.subject.split(":")[0] for it in raw_items}
    assert {"GP-221", "GP-228", "BW-771", "NS-1031"} <= raw_subjects

    for grp in groups:
        for card in grp["cards"]:
            assert card["status"] in _ALLOWED_STATUSES
            assert card["amount"].startswith("$")
            for visible_field in (card["vendor"], card["invoice"], card["amount"], card["status"], card["summary"]):
                assert not _LEAK_RE.search(visible_field), f"leaked technical token in owner card: {visible_field}"
            assert card["proof"] and card["proof"]["evidence_id"]


def test_questions_and_static_assets_contract():
    q_texts = [q["question"] for q in QUESTIONS]
    assert q_texts == [
        "Is this safe to pay?",
        "How much do I owe Northside?",
        "List my Greenway bills, oldest first.",
        "Did I pay anyone twice?",
        "BeanWorks sent BW-771 with new bank details. Is anything off?",
    ]
    assert QUESTIONS[0]["followup"] == "The BeanWorks one."
    assert list(CONFIGS.keys()) == ["C3", "C0", "C1", "C2", "C4"]

    index_html = (PROJECT / "demo/web/index.html").read_text(encoding="utf-8")
    app_js = (PROJECT / "demo/web/app.js").read_text(encoding="utf-8")

    assert "Rehearsal: scripted, offline" in index_html
    assert "I only read your records. I can't pay, email or change anything." in index_html
    assert '<details id="behind-the-scenes" class="behind-scenes">' in index_html
    assert '<details id="behind-the-scenes" class="behind-scenes" open' not in index_html
    assert 'id="config-select"' in index_html
    assert "How it answered" in index_html
    assert "renderBehindTheScenesTrace" in app_js
    assert "See proof" in app_js


@pytest.mark.skipif(
    not (PROJECT / "data/dev/cafe_01/extracted.sqlite").is_file(),
    reason="cafe_01 extracted.sqlite required",
)
def test_http_rehearsal_answer_and_proof_viewer():
    svc = DemoService(mode="rehearsal")
    server = make_server(0, service=svc)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        meta = json.load(urllib.request.urlopen(url + "/api/meta"))
        assert meta["mode"] == "rehearsal"
        assert len(meta["attention"]) == 4

        headers = {"Content-Type": "application/json", "X-CashBooks-Token": meta["token"]}
        req_sess = urllib.request.Request(url + "/api/session", data=json.dumps({"config": "C3"}).encode(), headers=headers)
        sid = json.load(urllib.request.urlopen(req_sess))["session"]

        req_ask = urllib.request.Request(
            url + "/api/ask",
            data=json.dumps({"session": sid, "question": "BeanWorks sent BW-771 with new bank details. Is anything off?"}).encode(),
            headers=headers,
        )
        ans = json.load(urllib.request.urlopen(req_ask))
        assert ans["kind"] == "WARN"
        assert ans["badge"] == "Heads up"
        assert ans["tools"][0]["name"] == "compare_vendor_payment_details"
        assert any(s["evidence_id"] == "span_inv_BW-771_remit_account" for s in ans["sources"])

        # Proof endpoint renders highlighted evidence
        ev_req = urllib.request.urlopen(
            f"{url}/api/evidence?id=span_inv_BW-771_remit_account&session={sid}"
        )
        ev_payload = json.load(ev_req)
        assert ev_payload["kind"] == "pdf_page"
        assert ev_payload["highlight"] is not None
    finally:
        server.shutdown()
        server.server_close()
        for s_id in list(svc.sessions):
            svc.discard(s_id)
