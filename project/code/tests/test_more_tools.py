"""Tests for the five tools added after the first slice, on the rendered café scenario."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from cashbooks.store.load_gold import load_gold
from cashbooks.tools.matching import descriptor_vendor, link_payments
from cashbooks.tools.registry import run_tool

CAFE = Path(__file__).resolve().parents[2] / "data" / "dev" / "cafe_01"
pytestmark = pytest.mark.skipif(not (CAFE / "invoices").exists(), reason="render the café bundle first")


@pytest.fixture(scope="module")
def store():
    s, report = load_gold(CAFE)
    assert report.ungrounded == []
    return s


def call(store, name, **args):
    return json.loads(run_tool(store, name, args))


def test_match_by_amount_and_date_skips_distractor(store):
    r = call(store, "match_payments", amount="842", posted_on="2026-09-12")
    assert r["outcome"] == "confirmed" and r["candidates"][0]["invoice_number"] == "NS-1048"


def test_unmatched_debit_has_no_candidates(store):
    r = call(store, "match_payments", amount="1750")
    assert r["outcome"] == "no_candidates" and "txn_0205" in r["why_undecided"]


def test_duplicate_payment_visible(store):
    r = call(store, "match_payments", invoice_number="NS-1031")
    assert [c["txn_id"] for c in r["candidates"]] == ["txn_0102", "txn_0109"]
    bills = call(store, "list_open_bills", as_of="2026-09-24", include_settled=True)["bills"]
    assert next(b for b in bills if b["invoice_number"] == "NS-1031")["state"] == "overpaid"


def test_sum_amount_due_per_vendor_and_overdue(store):
    r = call(store, "sum_amount_due", as_of="2026-09-30", vendor="Northside")
    assert r["totals"] == [{"amount": "1462.85", "currency": "USD"}]
    r = call(store, "sum_amount_due", as_of="2026-09-24", overdue_only=True)
    assert r["totals"] == [{"amount": "481.20", "currency": "USD"}]  # GP-221 268.90 + GP-228 212.30


def test_changed_payment_details_masked(store):
    r = call(store, "compare_vendor_payment_details", invoice_number="BW-771")
    assert r["outcome"] == "changed" and r["on_document"]["account_last4"] == "5507"
    assert "008812345507" not in json.dumps(r)
    assert call(store, "compare_vendor_payment_details", invoice_number="BW-760")["outcome"] == "same"


def test_summarize_purchases(store):
    r = call(store, "summarize_purchases", item="5 lb bag", date_from="2026-08-01", date_to="2026-08-31")
    assert r["quantities"] == [{"unit": "bag", "quantity": "12.00"}]
    r = call(store, "summarize_purchases", item="coffee", date_from="2026-08-01", date_to="2026-08-31")
    assert r["spend"] == [{"amount": "486.00", "currency": "USD"}]


def test_source_evidence_masks_and_labels(store):
    r = call(store, "get_source_evidence", evidence_ids=["span_msg_m01", "txn_0193", "vh_v_beanworks", "span_nope"])
    text = json.dumps(r)
    assert "008812345507" not in text and "********5507" in text
    assert r["missing"] == ["span_nope"]


def test_matcher_reproduces_ledger_links(store):
    gold = {(r[0], r[1]) for r in store.conn.execute("SELECT bill_id, txn_id FROM payment_links")}
    assert {(l.bill_id, l.txn_id) for l in link_payments(_fresh_without_links())} == gold


def _fresh_without_links():
    s, _ = load_gold(CAFE)
    s.conn.execute("DELETE FROM payment_links")
    return s


def test_descriptor_vendor():
    vendors = [{"vendor_id": "v1", "canonical_name": "Northside Supplies", "aliases": []},
               {"vendor_id": "v2", "canonical_name": "Greenway Produce", "aliases": []}]
    assert descriptor_vendor("NORTHSIDE SUP CO 8841", vendors) == "v1"
    assert descriptor_vendor("GREENWAY PRODUCE ACH", vendors) == "v2"
    assert descriptor_vendor("SQ *BAKERY DEPOT", vendors) is None
