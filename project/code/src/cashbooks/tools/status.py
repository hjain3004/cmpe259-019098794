"""Bill status, computed from confirmed payment links and credits as of a date.

Status is never inferred from what a document or message says: a vendor email
claiming "paid" does not change it. Such claims are reported as conflicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from cashbooks.contracts.common import Money, PaymentState
from cashbooks.contracts.records import Bill, LinkStatus
from cashbooks.contracts.tools import AppliedPayment, BillSummary
from cashbooks.normalize.fingerprint import mask_digits
from cashbooks.store.db import Store

ZERO = Decimal("0.00")
_MEMO_NOTE_RE = re.compile(
    r"\b(account|bank| banking|routing|remit(?:tance)?|pay\s+to|accounting\s+system|automated|system\s*:)",
    re.I,
)


def memo_has_note_outside_remit_fields(memo: str | None) -> bool:
    """True when a printed memo mentions bank/account/routing/remit details or system instructions."""
    if not memo:
        return False
    return _MEMO_NOTE_RE.search(" ".join(memo.split())) is not None


@dataclass
class BillState:
    bill: Bill
    paid: Decimal
    credited: Decimal
    remaining: Decimal
    state: PaymentState
    overdue: bool
    payments: list[AppliedPayment] = field(default_factory=list)
    possible_payments: list[AppliedPayment] = field(default_factory=list)
    remaining_if_candidates_apply: Decimal = ZERO
    credits: list[Money] = field(default_factory=list)
    credit_evidence: list[str] = field(default_factory=list)


def compute_state(store: Store, bill: Bill, as_of: date) -> BillState:
    paid = ZERO
    candidate_paid = ZERO
    payments: list[AppliedPayment] = []
    possible_payments: list[AppliedPayment] = []
    for link in store.links(bill.bill_id):
        txn = store.txn(link.txn_id)
        if txn is None or txn.posted_on > as_of:
            continue
        ap = AppliedPayment(
            txn_id=txn.txn_id, posted_on=txn.posted_on,
            amount_applied=Money(amount=link.amount_applied, currency=txn.currency),
            link_status=link.status.value,
            reasons=list(link.reasons),
        )
        if link.status is LinkStatus.CONFIRMED:
            payments.append(ap)
            paid += link.amount_applied
        else:
            possible_payments.append(ap)
            candidate_paid += link.amount_applied

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
    rem = max(remaining, ZERO)
    rem_with_cands = max(remaining - candidate_paid, ZERO)
    return BillState(
        bill, paid, credited, rem, state, overdue,
        payments, possible_payments, rem_with_cands, credits, credit_evidence,
    )


def bill_evidence(bill: Bill) -> list[str]:
    """Citable spans for the facts a status answer rests on."""
    keys = (
        "invoice_number", "total", "subtotal", "tax",
        "stated_due_date", "payment_terms", "issue_date",
        "reference_or_po", "memo",
    )
    return [bill.field_evidence[k] for k in keys if k in bill.field_evidence]


def summarize(store: Store, st: BillState) -> BillSummary:
    b = st.bill
    memo_span_id = b.field_evidence.get("memo")
    memo_span = store.span(memo_span_id) if memo_span_id else None
    memo_text = mask_digits(memo_span.quote) if memo_span else None
    has_note = memo_has_note_outside_remit_fields(memo_text)
    evidence = (
        bill_evidence(b)
        + [p.txn_id for p in st.payments]
        + [p.txn_id for p in st.possible_payments]
        + st.credit_evidence
    )
    rem_cand = (
        Money(amount=st.remaining_if_candidates_apply, currency=b.currency)
        if st.possible_payments
        else None
    )
    return BillSummary(
        bill_id=b.bill_id, invoice_number=b.invoice_number, vendor=store.vendor_name(b.vendor_id),
        printed_vendor_name=b.printed_vendor_name,
        issue_date=b.issue_date, due_date=b.due_date,
        total=Money(amount=b.total, currency=b.currency),
        remaining=Money(amount=st.remaining, currency=b.currency),
        remaining_if_candidates_apply=rem_cand,
        possible_payments=st.possible_payments,
        memo=memo_text,
        has_note_outside_remit_fields=has_note,
        state=st.state, overdue=st.overdue, evidence_ids=list(dict.fromkeys(evidence)),
    )
