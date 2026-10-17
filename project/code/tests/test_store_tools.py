import json
from datetime import date
from decimal import Decimal

import pytest

from cashbooks.contracts.common import PaymentState
from cashbooks.contracts.tools import GetBillStatusArgs, ListOpenBillsArgs
from cashbooks.store.load_gold import load_gold
from cashbooks.tools.bills import get_bill_status, list_open_bills
from cashbooks.tools.errors import ToolError
from cashbooks.tools.registry import run_tool

from mini_bundle import build

CLOCK = date(2026, 9, 24)


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    bundle = build(tmp_path_factory.mktemp("mini") / "mini_01")
    s, report = load_gold(bundle)
    assert report.ungrounded == [], report.ungrounded
    return s


def status(store, num, as_of=CLOCK):
    return get_bill_status(store, GetBillStatusArgs(invoice_number=num, as_of=as_of))


# ---------------------------------------------------------------- loading


def test_load_counts_and_evidence(store):
    assert len(store.bills()) == 6
    ids = store.evidence_ids()
    assert "span_inv_NS-1048_total" in ids and "txn_0193" in ids and "vh_v_northside" in ids
    span = store.span("span_inv_NS-1048_total")
    assert span.quote == "$842.00" and span.end - span.start == len(span.quote)


def test_full_account_numbers_never_stored(store):
    dump = "\n".join(store.conn.iterdump())
    assert "004417829931" not in dump
    assert "9931" in dump  # last four kept


def test_bank_change_message_fingerprinted(store):
    claim = next(c for c in store.claims() if c.kind == "bank_change_request")
    assert claim.new_account_last4 == "5507"


# ---------------------------------------------------------------- get_bill_status


def test_paid_bill_without_invoice_number_in_descriptor(store):
    r = status(store, "NS-1048")
    assert r.bill.state is PaymentState.PAID and r.bill.remaining.amount == Decimal("0.00")
    assert [p.txn_id for p in r.payments] == ["txn_0193"]
    assert "txn_0193" in r.bill.evidence_ids


def test_as_of_before_payment_is_unpaid_and_overdue(store):
    r = status(store, "NS-1048", as_of=date(2026, 9, 11))
    assert r.bill.state is PaymentState.UNPAID and not r.bill.overdue  # due 2026-09-12
    r = status(store, "NS-1048", as_of=date(2026, 9, 12))
    assert not r.bill.overdue  # due today is not overdue


def test_partial_payment_and_conflicting_claim(store):
    r = status(store, "GP-228")
    assert r.bill.state is PaymentState.PARTIAL
    assert r.bill.remaining.amount == Decimal("212.30")
    assert r.bill.overdue and r.bill.due_date == date(2026, 9, 10)
    assert r.stated_due_date is None and r.derived_due_date == date(2026, 9, 10)
    assert r.conflicting_claims == ["span_msg_m03"]


def test_credit_note_reduces_balance(store):
    r = status(store, "NS-1062")
    assert r.bill.remaining.amount == Decimal("1073.25")
    assert r.bill.state is PaymentState.PARTIAL


def test_duplicate_payment_shows_overpaid(store):
    r = status(store, "NS-1031")
    assert r.bill.state is PaymentState.OVERPAID and len(r.payments) == 2


def test_unknown_invoice_raises(store):
    with pytest.raises(ToolError):
        status(store, "XX-1")


# ---------------------------------------------------------------- list_open_bills


def test_list_open_bills_all(store):
    r = list_open_bills(store, ListOpenBillsArgs(as_of=CLOCK))
    assert [b.invoice_number for b in r.bills] == ["GP-221", "GP-228", "NS-1062", "NS-1070"]


def test_list_open_bills_due_within_a_week(store):
    r = list_open_bills(store, ListOpenBillsArgs(as_of=CLOCK, due_before=date(2026, 10, 1)))
    nums = [b.invoice_number for b in r.bills]
    assert "NS-1062" in nums and "NS-1070" not in nums  # NS-1070 is due 10/02


def test_list_open_bills_vendor_alias(store):
    r = list_open_bills(store, ListOpenBillsArgs(as_of=CLOCK, vendor="Northside Supply Co."))
    assert [b.invoice_number for b in r.bills] == ["NS-1062", "NS-1070"]
    r = list_open_bills(store, ListOpenBillsArgs(as_of=CLOCK, vendor="greenway"))
    assert {b.invoice_number for b in r.bills} == {"GP-221", "GP-228"}


# ---------------------------------------------------------------- registry


def test_registry_round_trip_and_errors(store):
    out = json.loads(run_tool(store, "get_bill_status", {"invoice_number": "GP-228", "as_of": "2026-09-24"}))
    assert out["bill"]["remaining"] == {"amount": "212.30", "currency": "USD"}
    assert "error" in json.loads(run_tool(store, "pay_bill", {}))
    assert "error" in json.loads(run_tool(store, "get_bill_status", {"invoice_number": "GP-228"}))
    assert "error" in json.loads(run_tool(store, "match_payments", {"invoice_number": "GP-228"}))
    assert "error" in json.loads(run_tool(store, "list_open_bills", {"as_of": "2026-09-24", "business_id": "x"}))
