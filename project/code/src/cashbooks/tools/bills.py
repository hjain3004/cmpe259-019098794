"""Read-only tools: get_bill_status and list_open_bills."""

from __future__ import annotations

from decimal import Decimal

from cashbooks.contracts.common import Money, PaymentState
from cashbooks.contracts.tools import (
    BillLineItem, GetBillStatusArgs, GetBillStatusResult, ListOpenBillsArgs, ListOpenBillsResult,
)
from cashbooks.normalize.vendors import resolve_vendor
from cashbooks.store.db import Store
from cashbooks.tools.errors import ToolError
from cashbooks.tools.status import compute_state, summarize


def _vendor_filter(store: Store, vendor: str | None) -> set[str] | None:
    if not vendor:
        return None
    cands = resolve_vendor(vendor, store.vendor_dicts())
    if not cands:
        raise ToolError(f"no known vendor matches {vendor!r}")
    return {c.vendor_id for c in cands}


def get_bill_status(store: Store, args: GetBillStatusArgs) -> GetBillStatusResult:
    if args.bill_id:
        bill = store.bill(args.bill_id)
        bills = [bill] if bill else []
    else:
        bills = store.bills_by_invoice_number(args.invoice_number or "")
    if not bills:
        raise ToolError(f"no bill found for {args.invoice_number or args.bill_id!r}")
    if len(bills) > 1:
        nums = ", ".join(b.bill_id for b in bills)
        raise ToolError(f"invoice number is ambiguous; matching bill_ids: {nums}")
    bill = bills[0]
    st = compute_state(store, bill, args.as_of)

    conflicts = [
        c.evidence_id
        for c in store.claims()
        if c.kind == "payment_claim"
        and bill.invoice_number.upper() in (r.upper() for r in c.invoice_refs)
        and st.state is not PaymentState.PAID
    ]
    summary = summarize(store, st)
    lines = store.lines(bill.bill_id)
    line_items = [
        BillLineItem(
            line_no=ln.line_no,
            description=ln.description,
            quantity=ln.quantity,
            unit=ln.unit,
            unit_price=ln.unit_price,
            line_total=Money(amount=ln.line_total, currency=bill.currency) if ln.line_total is not None else None,
            evidence_id=ln.evidence_id,
        )
        for ln in lines
    ]
    line_totals = [ln.line_total for ln in lines if ln.line_total is not None]
    lines_sum_dec = sum(line_totals, Decimal("0.00")) if line_totals else None
    lines_sum = Money(amount=lines_sum_dec, currency=bill.currency) if lines_sum_dec is not None else None
    lines_match_sub = (
        (lines_sum_dec == bill.subtotal)
        if (lines_sum_dec is not None and bill.subtotal is not None)
        else None
    )
    total_matches = (
        (bill.subtotal + (bill.tax or Decimal("0.00")) == bill.total)
        if bill.subtotal is not None
        else (lines_sum_dec == bill.total if lines_sum_dec is not None else None)
    )
    ref_span_id = bill.field_evidence.get("reference_or_po")
    ref_span = store.span(ref_span_id) if ref_span_id else None
    ref_text = ref_span.quote if ref_span else None
    return GetBillStatusResult(
        bill=summary,
        subtotal=Money(amount=bill.subtotal, currency=bill.currency) if bill.subtotal is not None else None,
        tax=Money(amount=bill.tax, currency=bill.currency) if bill.tax is not None else None,
        line_items=line_items,
        line_items_sum=lines_sum,
        line_items_match_subtotal=lines_match_sub,
        total_matches_subtotal_plus_tax=total_matches,
        reference_or_po=ref_text,
        memo=summary.memo,
        has_note_outside_remit_fields=summary.has_note_outside_remit_fields,
        stated_due_date=bill.stated_due_date,
        derived_due_date=bill.due_date_derived,
        due_date_calculation=bill.due_date_calculation,
        due_date_conflict=bill.due_date_conflict,
        payments=st.payments,
        possible_payments=st.possible_payments,
        remaining_if_candidates_apply=summary.remaining_if_candidates_apply,
        credits=st.credits,
        conflicting_claims=conflicts,
    )


def list_open_bills(store: Store, args: ListOpenBillsArgs) -> ListOpenBillsResult:
    vendor_ids = _vendor_filter(store, args.vendor)
    out = []
    for bill in store.bills():
        if bill.issue_date > args.as_of:
            continue
        if vendor_ids is not None and bill.vendor_id not in vendor_ids:
            continue
        st = compute_state(store, bill, args.as_of)
        if not args.include_settled and st.state not in (PaymentState.UNPAID, PaymentState.PARTIAL):
            continue
        due = bill.due_date
        if args.due_before is not None and (due is None or due > args.due_before):
            continue
        out.append(summarize(store, st))
    out.sort(key=lambda s: (s.due_date is None, s.due_date, s.invoice_number))
    return ListOpenBillsResult(as_of=args.as_of, bills=out)
