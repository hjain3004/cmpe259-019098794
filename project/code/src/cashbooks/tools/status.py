"""Bill status, computed from confirmed payment links and credits as of a date.

Status is never inferred from what a document or message says: a vendor email
claiming "paid" does not change it. Such claims are reported as conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from cashbooks.contracts.common import Money, PaymentState
from cashbooks.contracts.records import Bill, LinkStatus
from cashbooks.contracts.tools import AppliedPayment, BillSummary
from cashbooks.store.db import Store

ZERO = Decimal("0.00")


@dataclass
class BillState:
    bill: Bill
    paid: Decimal
    credited: Decimal
    remaining: Decimal
    state: PaymentState
    overdue: bool
    payments: list[AppliedPayment] = field(default_factory=list)
    credits: list[Money] = field(default_factory=list)
    credit_evidence: list[str] = field(default_factory=list)


def compute_state(store: Store, bill: Bill, as_of: date) -> BillState:
    paid = ZERO
    payments: list[AppliedPayment] = []
    for link in store.links(bill.bill_id):
        txn = store.txn(link.txn_id)
        if txn is None or txn.posted_on > as_of:
            continue
        payments.append(AppliedPayment(
            txn_id=txn.txn_id, posted_on=txn.posted_on,
            amount_applied=Money(amount=link.amount_applied, currency=txn.currency),
            link_status=link.status.value,
        ))
        if link.status is LinkStatus.CONFIRMED:
            paid += link.amount_applied

    credited = ZERO
    credits: list[Money] = []
    credit_evidence: list[str] = []
    for c in store.credits(bill.bill_id):
        if c.issued_on <= as_of:
            credited += c.amount
            credits.append(Money(amount=c.amount, currency=bill.currency))
            credit_evidence.append(c.evidence_id)

    settled = paid + credited
    remaining = bill.total - settled
    if settled == ZERO:
        state = PaymentState.UNPAID
    elif remaining > ZERO:
        state = PaymentState.PARTIAL
    elif remaining == ZERO:
        state = PaymentState.PAID
    else:
        state = PaymentState.OVERPAID
    due = bill.due_date
    overdue = state in (PaymentState.UNPAID, PaymentState.PARTIAL) and due is not None and due < as_of
    return BillState(bill, paid, credited, max(remaining, ZERO), state, overdue, payments, credits, credit_evidence)


def bill_evidence(bill: Bill) -> list[str]:
    """Citable spans for the facts a status answer rests on."""
    keys = ("invoice_number", "total", "stated_due_date", "payment_terms", "issue_date")
    return [bill.field_evidence[k] for k in keys if k in bill.field_evidence]


def summarize(store: Store, st: BillState) -> BillSummary:
    b = st.bill
    evidence = bill_evidence(b) + [p.txn_id for p in st.payments] + st.credit_evidence
    return BillSummary(
        bill_id=b.bill_id, invoice_number=b.invoice_number, vendor=store.vendor_name(b.vendor_id),
        issue_date=b.issue_date, due_date=b.due_date,
        total=Money(amount=b.total, currency=b.currency),
        remaining=Money(amount=st.remaining, currency=b.currency),
        state=st.state, overdue=st.overdue, evidence_ids=list(dict.fromkeys(evidence)),
    )
