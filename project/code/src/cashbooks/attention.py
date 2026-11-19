"""Deterministic attention-item scanner over a Store (no LLM calls)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from cashbooks.contracts.common import PaymentState
from cashbooks.contracts.postprocess import mask_numbers
from cashbooks.contracts.tools import (
    CompareVendorPaymentDetailsArgs,
    GetBillStatusArgs,
    ListOpenBillsArgs,
    MatchPaymentsArgs,
)
from cashbooks.store.db import Store
from cashbooks.tools.bills import get_bill_status, list_open_bills
from cashbooks.tools.more import compare_vendor_payment_details, match_payments

ATTENTION_TYPES = (
    "overdue_bill",
    "duplicate_bill",
    "duplicate_payment",
    "partial_payment",
    "candidate_payment_link",
    "unmatched_bank_debit",
    "bank_detail_mismatch",
    "total_mismatch",
    "due_date_conflict",
    "message_conflict",
)


@dataclass(frozen=True)
class AttentionItem:
    kind: str
    subject: str
    description: str
    evidence_ids: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    return mask_numbers(text)


def find_attention_items(store: Store, as_of: date) -> list[AttentionItem]:
    """Scan a business Store at as_of using read-only tools and store queries."""
    items: list[AttentionItem] = []

    # Enumerate bills directly from Store (to obtain vendor_id for duplicate grouping).
    bills = [b for b in store.bills() if b.issue_date <= as_of]
    all_summaries = list_open_bills(store, ListOpenBillsArgs(as_of=as_of, include_settled=True)).bills
    summary_by_id = {s.bill_id: s for s in all_summaries}

    seen_dup_keys: dict[tuple, str] = {}
    linked_txn_ids: set[str] = set()

    for b in bills:
        st = get_bill_status(store, GetBillStatusArgs(bill_id=b.bill_id, as_of=as_of))
        bsum = st.bill
        vname = bsum.vendor

        for p in st.payments:
            linked_txn_ids.add(p.txn_id)
        for pp in st.possible_payments:
            linked_txn_ids.add(pp.txn_id)

        # 1. overdue_bill
        if bsum.overdue:
            items.append(AttentionItem(
                kind="overdue_bill",
                subject=b.invoice_number,
                description=_clean(
                    f"{b.invoice_number} ({vname}) is overdue: "
                    f"{bsum.remaining.amount:.2f} {bsum.remaining.currency} due {bsum.due_date}."
                ),
                evidence_ids=list(bsum.evidence_ids),
            ))

        # 2. duplicate_bill (same vendor, total, issue_date, and PO)
        dup_key = (b.vendor_id, b.total, b.issue_date, st.reference_or_po)
        if dup_key in seen_dup_keys:
            orig = seen_dup_keys[dup_key]
            items.append(AttentionItem(
                kind="duplicate_bill",
                subject=b.invoice_number,
                description=_clean(
                    f"{b.invoice_number} ({vname}) matches {orig} on vendor, "
                    f"amount ({b.total:.2f} {b.currency}), and date ({b.issue_date})."
                ),
                evidence_ids=list(bsum.evidence_ids[:2]),
            ))
        else:
            seen_dup_keys[dup_key] = b.invoice_number

        # 3. duplicate_payment
        paid_amt = sum((p.amount_applied.amount for p in st.payments), Decimal("0.00"))
        if bsum.state is PaymentState.OVERPAID or (len(st.payments) > 1 and paid_amt > b.total):
            items.append(AttentionItem(
                kind="duplicate_payment",
                subject=b.invoice_number,
                description=_clean(
                    f"{b.invoice_number} ({vname}) has {len(st.payments)} confirmed payments "
                    f"totalling {paid_amt:.2f} {b.currency} against {b.total:.2f}."
                ),
                evidence_ids=[p.txn_id for p in st.payments] + list(bsum.evidence_ids[:1]),
            ))

        # 4. partial_payment
        if bsum.state is PaymentState.PARTIAL and st.payments:
            items.append(AttentionItem(
                kind="partial_payment",
                subject=b.invoice_number,
                description=_clean(
                    f"{b.invoice_number} ({vname}) is partially paid: "
                    f"{paid_amt:.2f} paid, {bsum.remaining.amount:.2f} {bsum.remaining.currency} remaining."
                ),
                evidence_ids=[p.txn_id for p in st.payments] + list(bsum.evidence_ids[:1]),
            ))

        # 5. candidate_payment_link
        for pp in st.possible_payments:
            items.append(AttentionItem(
                kind="candidate_payment_link",
                subject=f"{b.invoice_number}:{pp.txn_id}",
                description=_clean(
                    f"Possible payment {pp.txn_id} ({pp.amount_applied.amount:.2f} {pp.amount_applied.currency} "
                    f"on {pp.posted_on}) for {b.invoice_number}, not confirmed."
                ),
                evidence_ids=[pp.txn_id] + list(bsum.evidence_ids[:1]),
            ))

        # 7. bank_detail_mismatch
        if b.vendor_id:
            cmp = compare_vendor_payment_details(store, CompareVendorPaymentDetailsArgs(invoice_number=b.invoice_number))
            if cmp.outcome == "changed":
                items.append(AttentionItem(
                    kind="bank_detail_mismatch",
                    subject=b.invoice_number,
                    description=_clean(f"{b.invoice_number} ({vname}): " + "; ".join(cmp.differences) + "."),
                    evidence_ids=list(cmp.document_evidence) + list(cmp.history_evidence),
                ))

        # 8. total_mismatch
        if st.line_items_match_subtotal is False or st.total_matches_subtotal_plus_tax is False:
            ev = [b.field_evidence["total"]] if "total" in b.field_evidence else list(bsum.evidence_ids[:1])
            items.append(AttentionItem(
                kind="total_mismatch",
                subject=b.invoice_number,
                description=_clean(
                    f"{b.invoice_number} ({vname}): line items or subtotal+tax do not match stated total "
                    f"{b.total:.2f} {b.currency}."
                ),
                evidence_ids=ev,
            ))

        # 9. due_date_conflict
        if st.due_date_conflict:
            ev = [
                b.field_evidence[k]
                for k in ("stated_due_date", "payment_terms", "issue_date")
                if k in b.field_evidence
            ]
            items.append(AttentionItem(
                kind="due_date_conflict",
                subject=b.invoice_number,
                description=_clean(
                    f"{b.invoice_number} ({vname}): stated due date {st.stated_due_date} "
                    f"conflicts with derived due date {st.derived_due_date}."
                ),
                evidence_ids=ev or list(bsum.evidence_ids[:1]),
            ))

        # 10. message_conflict
        if st.conflicting_claims:
            items.append(AttentionItem(
                kind="message_conflict",
                subject=b.invoice_number,
                description=_clean(
                    f"{b.invoice_number} ({vname}): vendor message claims payment not confirmed in bank records."
                ),
                evidence_ids=list(st.conflicting_claims) + list(bsum.evidence_ids[:1]),
            ))

    # 6. unmatched_bank_debit (enumerate bank txns directly from Store)
    for txn in store.txns():
        if txn.amount >= 0 or txn.posted_on > as_of or txn.txn_id in linked_txn_ids:
            continue
        res = match_payments(store, MatchPaymentsArgs(txn_id=txn.txn_id))
        if res.outcome == "no_candidates":
            items.append(AttentionItem(
                kind="unmatched_bank_debit",
                subject=txn.txn_id,
                description=_clean(
                    f"{txn.txn_id} ({txn.posted_on}, {txn.descriptor}): "
                    f"{abs(txn.amount):.2f} {txn.currency} debit has no matching bill."
                ),
                evidence_ids=[txn.txn_id],
            ))

    return items
