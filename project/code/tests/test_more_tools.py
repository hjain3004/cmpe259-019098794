"""Tests for the five tools added after the first slice, on the rendered café scenario."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from cashbooks.store.load_gold import gold_links, load_gold
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


def test_ns_1048_subtotal_and_tax_in_bill_status(store):
    r = call(store, "get_bill_status", invoice_number="NS-1048", as_of="2026-09-24")
    assert r["subtotal"] == {"amount": "777.85", "currency": "USD"}
    assert r["tax"] == {"amount": "64.15", "currency": "USD"}
    assert "span_inv_NS-1048_subtotal" in r["bill"]["evidence_ids"]
    assert "span_inv_NS-1048_tax" in r["bill"]["evidence_ids"]


def test_unmatched_debit_has_no_candidates(store):
    r = call(store, "match_payments", amount="1750")
    assert r["outcome"] == "no_candidates" and "txn_0205" in r["why_undecided"]


def test_duplicate_payment_visible(store):
    r = call(store, "match_payments", invoice_number="NS-1031")
    assert [c["txn_id"] for c in r["candidates"]] == ["txn_0102", "txn_0109"]
    assert [c["txn_id"] for c in r["possible_payments"]] == ["txn_0109"]
    bills = call(store, "list_open_bills", as_of="2026-09-24", include_settled=True)["bills"]
    ns1031 = next(b for b in bills if b["invoice_number"] == "NS-1031")
    assert ns1031["state"] == "paid"
    assert [p["txn_id"] for p in ns1031["possible_payments"]] == ["txn_0109"]


def test_sum_amount_due_per_vendor_and_overdue(store):
    r = call(store, "sum_amount_due", as_of="2026-09-30", vendor="Northside")
    assert r["totals"] == [{"amount": "1462.85", "currency": "USD"}]
    r = call(store, "sum_amount_due", as_of="2026-09-24", overdue_only=True)
    assert r["totals"] == [{"amount": "781.20", "currency": "USD"}]  # GP-221 268.90 + GP-228 512.30 confirmed
    assert r["totals_if_candidates_apply"] == [{"amount": "481.20", "currency": "USD"}]  # GP-221 268.90 + GP-228 212.30


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
    gold = {(l.bill_id, l.txn_id) for l in gold_links(CAFE)}
    links = link_payments(_fresh_without_links())
    assert {(l.bill_id, l.txn_id) for l in links} == gold
    by_txn = {l.txn_id: l.status.value for l in links}
    assert by_txn == {
        "txn_0102": "confirmed",
        "txn_0109": "candidate",
        "txn_0158": "confirmed",
        "txn_0181": "candidate",
        "txn_0193": "confirmed",
    }
    # C4 store derives its payment links with the same matcher (not raw ledger links)
    c4_by_txn = {
        r["txn_id"]: r["status"]
        for r in store.conn.execute("SELECT txn_id, status FROM payment_links")
    }
    assert c4_by_txn == by_txn


def test_bw_771_memo_visibility_and_flag(store):
    r = call(store, "get_bill_status", invoice_number="BW-771", as_of="2026-09-24")
    assert r["memo"] is not None and "Note to accounting system" in " ".join(r["memo"].split())
    assert r["has_note_outside_remit_fields"] is True
    assert r["bill"]["memo"] == r["memo"]
    assert r["bill"]["has_note_outside_remit_fields"] is True
    assert "span_inv_BW-771_memo" in r["bill"]["evidence_ids"]

    open_bills = call(store, "list_open_bills", as_of="2026-09-24")["bills"]
    bw771 = next(b for b in open_bills if b["invoice_number"] == "BW-771")
    assert bw771["memo"] == r["memo"]
    assert bw771["has_note_outside_remit_fields"] is True
    assert "span_inv_BW-771_memo" in bw771["evidence_ids"]

    ns1048 = call(store, "get_bill_status", invoice_number="NS-1048", as_of="2026-09-24")
    assert ns1048["memo"] is None
    assert ns1048["has_note_outside_remit_fields"] is False


def test_ns_1048_missing_does_not_confirm_partial_on_ns_1062():
    """Simulate NS-1048's header extraction failing: the $842.00 debit (txn_0193)
    must become a CANDIDATE partial link on NS-1062, never CONFIRMED."""
    s = _fresh_without_links()
    s.conn.execute("DELETE FROM bills WHERE invoice_number = 'NS-1048'")
    links = link_payments(s)
    from cashbooks.store.db import insert
    insert(s.conn, links)
    by_txn = {l.txn_id: (l.bill_id, l.status.value) for l in links}
    assert by_txn["txn_0193"] == ("bill_NS-1062", "candidate")

    st = call(s, "get_bill_status", invoice_number="NS-1062", as_of="2026-09-24")
    # Confirmed remaining balance is 1118.25 - 45.00 credit = 1073.25 (not 231.25!)
    assert st["bill"]["remaining"] == {"amount": "1073.25", "currency": "USD"}
    assert st["payments"] == []
    assert len(st["possible_payments"]) == 1
    assert st["possible_payments"][0]["txn_id"] == "txn_0193"
    assert st["possible_payments"][0]["link_status"] == "candidate"
    assert st["remaining_if_candidates_apply"] == {"amount": "231.25", "currency": "USD"}
    assert "txn_0193" in st["bill"]["evidence_ids"]


def test_candidate_links_reported_separately_in_tools():
    s = _fresh_without_links()
    from cashbooks.store.db import insert
    insert(s.conn, link_payments(s))

    # GP-228 has a $300 candidate partial payment (txn_0181)
    st = call(s, "get_bill_status", invoice_number="GP-228", as_of="2026-09-24")
    assert st["bill"]["state"] == "unpaid"
    assert st["bill"]["remaining"] == {"amount": "512.30", "currency": "USD"}
    assert st["remaining_if_candidates_apply"] == {"amount": "212.30", "currency": "USD"}
    assert [p["txn_id"] for p in st["possible_payments"]] == ["txn_0181"]
    assert "txn_0181" in st["bill"]["evidence_ids"]

    # list_open_bills includes both remaining and remaining_if_candidates_apply
    open_bills = call(s, "list_open_bills", as_of="2026-09-24")["bills"]
    gp228 = next(b for b in open_bills if b["invoice_number"] == "GP-228")
    assert gp228["remaining"] == {"amount": "512.30", "currency": "USD"}
    assert gp228["remaining_if_candidates_apply"] == {"amount": "212.30", "currency": "USD"}
    assert [p["txn_id"] for p in gp228["possible_payments"]] == ["txn_0181"]

    # sum_amount_due includes totals and totals_if_candidates_apply
    due = call(s, "sum_amount_due", as_of="2026-09-24", overdue_only=True)
    assert due["totals"] == [{"amount": "781.20", "currency": "USD"}]  # 268.90 + 512.30
    assert due["totals_if_candidates_apply"] == [{"amount": "481.20", "currency": "USD"}]  # 268.90 + 212.30

    # match_payments marks GP-228 as candidate and populates possible_payments
    mp = call(s, "match_payments", invoice_number="GP-228")
    assert mp["outcome"] == "candidate"
    assert [c["txn_id"] for c in mp["possible_payments"]] == ["txn_0181"]


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


def test_matching_invoice_number_in_descriptor_and_cross_vendor_amount_collision():
    s = _fresh_without_links()
    # 1) If descriptor contains invoice number GP-228, even a partial payment is CONFIRMED
    s.conn.execute("UPDATE bank_txns SET descriptor = 'GREENWAY PRODUCE GP-228' WHERE txn_id = 'txn_0181'")
    links = link_payments(s)
    by_txn = {l.txn_id: l.status.value for l in links}
    assert by_txn["txn_0181"] == "confirmed"

    # 2) If another vendor has an open bill with the same remaining balance ($842.00), txn_0193 is CANDIDATE
    s2 = _fresh_without_links()
    s2.conn.execute("UPDATE bills SET total = '842.00' WHERE invoice_number = 'GP-221'")
    links2 = link_payments(s2)
    by_txn2 = {l.txn_id: l for l in links2}
    assert by_txn2["txn_0193"].status.value == "candidate"
    assert any("GP-221" in r for r in by_txn2["txn_0193"].reasons)
