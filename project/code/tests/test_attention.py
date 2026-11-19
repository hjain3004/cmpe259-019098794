"""Unit tests for cashbooks.attention and evaluation/attention_eval.py."""

from __future__ import annotations

import importlib.util
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from cashbooks.attention import ATTENTION_TYPES, find_attention_items
from cashbooks.contracts.records import (
    BankTxn,
    Bill,
    BillLine,
    Document,
    DocumentKind,
    EvidenceSpan,
    LinkStatus,
    MessageClaim,
    PaymentLink,
    Vendor,
    VendorFingerprint,
)
from cashbooks.normalize.fingerprint import fingerprint
from cashbooks.normalize.terms import parse_terms
from cashbooks.store.db import Store, connect, insert

PROJECT = Path(__file__).resolve().parents[2]
CAFE = PROJECT / "data" / "dev" / "cafe_01"
AS_OF = date(2026, 9, 24)


def _bill(
    bill_id: str,
    inv: str,
    issue: date,
    total: str,
    due_stated: date | None = None,
    due_derived: date | None = None,
    acct_hash: str | None = None,
    acct_last4: str | None = None,
) -> Bill:
    doc_id = f"doc_{inv}"
    return Bill(
        business_id="b1",
        bill_id=bill_id,
        vendor_id="v1",
        doc_id=doc_id,
        invoice_number=inv,
        issue_date=issue,
        stated_due_date=due_stated,
        payment_terms_raw="Net 15",
        terms_kind=parse_terms("Net 15").kind,
        net_days=15,
        due_date_derived=due_derived,
        due_date_calculation="issue + 15d",
        currency="USD",
        subtotal=Decimal(total),
        tax=Decimal("0.00"),
        total=Decimal(total),
        remit_account_hash=acct_hash,
        remit_account_last4=acct_last4,
        remit_bank_name="Test Bank",
        field_evidence={"total": f"span_{inv}_total"},
    )


def test_find_attention_items_all_ten_types():
    conn = connect(":memory:")
    good_h, good4 = fingerprint("001122334417")
    bad_h, bad4 = fingerprint("009988775507")

    records = [
        Vendor(business_id="b1", vendor_id="v1", canonical_name="Acme Coffee"),
        VendorFingerprint(
            business_id="b1",
            vendor_id="v1",
            evidence_id="vh_v1",
            account_hash=good_h,
            account_last4=good4,
            bank_name="Test Bank",
            verified_on=date(2026, 1, 1),
        ),
        # Bills:
        # 1. B1: overdue + due_date_conflict + message_conflict + bank_detail_mismatch
        _bill("b_1", "INV-1", date(2026, 8, 1), "100.00", date(2026, 8, 10), date(2026, 8, 16), bad_h, bad4),
        # 2 & 3. B2 and B2_DUP: duplicate_bill + total_mismatch (B2 paid once, B2_DUP unpaid & not overdue)
        _bill("b_2", "INV-2", date(2026, 9, 15), "200.00", date(2026, 9, 30), date(2026, 9, 30), good_h, good4),
        _bill("b_2d", "INV-2B", date(2026, 9, 15), "200.00", date(2026, 9, 30), date(2026, 9, 30), good_h, good4),
        # 4. B3: duplicate_payment
        _bill("b_3", "INV-3", date(2026, 9, 10), "50.00", date(2026, 9, 25), date(2026, 9, 25), good_h, good4),
        # 5. B4: partial_payment
        _bill("b_4", "INV-4", date(2026, 9, 12), "300.00", date(2026, 9, 27), date(2026, 9, 27), good_h, good4),
        # 6. B5: candidate_payment_link
        _bill("b_5", "INV-5", date(2026, 9, 14), "400.00", date(2026, 9, 29), date(2026, 9, 29), good_h, good4),
        # Line item mismatch on INV-2 (line_total 150 != subtotal 200)
        BillLine(
            business_id="b1", bill_id="b_2", line_no=1, description="Beans",
            line_total=Decimal("150.00"), evidence_id="span_INV-2_total",
        ),
        # Evidence spans
        *[
            EvidenceSpan(
                business_id="b1", span_id=f"span_{inv}_total", doc_id=f"doc_{inv}",
                page=1, start=0, end=5, quote="10.00",
            )
            for inv in ("INV-1", "INV-2", "INV-2B", "INV-3", "INV-4", "INV-5")
        ],
        Document(business_id="b1", doc_id="msg_m1", kind=DocumentKind.MESSAGE, path="messages.jsonl", received_on=date(2026, 9, 15)),
        EvidenceSpan(business_id="b1", span_id="span_msg_m1", doc_id="msg_m1", page=1, start=0, end=4, quote="paid"),
        MessageClaim(
            business_id="b1", claim_id="c1", doc_id="msg_m1", kind="payment_claim",
            invoice_refs=["INV-1"], evidence_id="span_msg_m1",
        ),
        # Bank txns
        BankTxn(business_id="b1", txn_id="txn_2", posted_on=date(2026, 9, 16), amount=Decimal("-200.00"), currency="USD", descriptor="ACME INV-2"),
        BankTxn(business_id="b1", txn_id="txn_3a", posted_on=date(2026, 9, 11), amount=Decimal("-50.00"), currency="USD", descriptor="ACME INV-3"),
        BankTxn(business_id="b1", txn_id="txn_3b", posted_on=date(2026, 9, 12), amount=Decimal("-50.00"), currency="USD", descriptor="ACME INV-3"),
        BankTxn(business_id="b1", txn_id="txn_4", posted_on=date(2026, 9, 13), amount=Decimal("-100.00"), currency="USD", descriptor="ACME INV-4"),
        BankTxn(business_id="b1", txn_id="txn_5", posted_on=date(2026, 9, 15), amount=Decimal("-400.00"), currency="USD", descriptor="ACME"),
        BankTxn(business_id="b1", txn_id="txn_unm", posted_on=date(2026, 9, 18), amount=Decimal("-999.00"), currency="USD", descriptor="MYSTERY WIRE 001122334455"),
        # Payment links
        PaymentLink(business_id="b1", bill_id="b_2", txn_id="txn_2", amount_applied=Decimal("200.00"), status=LinkStatus.CONFIRMED, reasons=["inv"]),
        PaymentLink(business_id="b1", bill_id="b_3", txn_id="txn_3a", amount_applied=Decimal("50.00"), status=LinkStatus.CONFIRMED, reasons=["inv"]),
        PaymentLink(business_id="b1", bill_id="b_3", txn_id="txn_3b", amount_applied=Decimal("50.00"), status=LinkStatus.CONFIRMED, reasons=["inv"]),
        PaymentLink(business_id="b1", bill_id="b_4", txn_id="txn_4", amount_applied=Decimal("100.00"), status=LinkStatus.CONFIRMED, reasons=["inv"]),
        PaymentLink(business_id="b1", bill_id="b_5", txn_id="txn_5", amount_applied=Decimal("400.00"), status=LinkStatus.CANDIDATE, reasons=["amt"]),
    ]
    insert(conn, records)
    store = Store(conn, "b1")
    items = find_attention_items(store, AS_OF)
    found_kinds = {it.kind for it in items}
    for kind in ATTENTION_TYPES:
        assert kind in found_kinds, f"missing {kind}"
    for it in items:
        assert not re.search(r"\b\d{6,}\b", it.description), f"unmasked digits in {it.description}"
        assert len(it.evidence_ids) >= 1


def test_attention_eval_on_cafe_01():
    spec = importlib.util.spec_from_file_location("attention_eval", PROJECT / "evaluation" / "attention_eval.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["attention_eval"] = mod
    spec.loader.exec_module(mod)

    rep = mod.evaluate_bundles(dev_bundles=[CAFE], heldout_bundles=[])
    c4 = rep["dev"]["cafe_01"]["C4"]
    assert c4["expected"] == 13
    assert c4["tp"] == 11
    assert c4["by_type"]["overdue_bill"]["recall"] == 1.0
    assert c4["by_type"]["bank_detail_mismatch"]["recall"] == 1.0
    assert c4["by_type"]["message_conflict"]["recall"] == 1.0
