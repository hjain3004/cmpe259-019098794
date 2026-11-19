"""Deterministic payment matching: which bank debit pays which bill.

Used two ways: by match_payments to explain candidates to the model, and by the
extracted-records loader to create payment links (the gold loader takes links
from the ledger instead). Thresholds were set on development bundles only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from cashbooks.contracts.records import BankTxn, Bill, LinkStatus, PaymentLink
from cashbooks.normalize.vendors import normalize_name
from cashbooks.store.db import Store

LATE_WINDOW_DAYS = 45  # a payment may land up to 45 days after the due date
_NOISE = re.compile(r"\b(ach|pmt|payment|online|transfer|ref|co|inc|llc|sq|pos|debit)\b")


def descriptor_key(descriptor: str) -> str:
    """'NORTHSIDE SUP CO 8841' -> 'northside sup'."""
    s = re.sub(r"[^a-z ]", " ", descriptor.lower())
    s = _NOISE.sub(" ", s)
    return " ".join(s.split())


def descriptor_vendor(descriptor: str, vendors: list[dict]) -> str | None:
    """Vendor whose name or verified alias starts with the descriptor's first word."""
    key = descriptor_key(descriptor).split()
    if not key:
        return None
    hits = set()
    for v in vendors:
        names = [v["canonical_name"]] + [a["alias"] for a in v.get("aliases", []) if a.get("verified")]
        for n in names:
            toks = normalize_name(n).replace(" ", "").lower()
            if toks.startswith(key[0]) or normalize_name(n).split()[0] == key[0]:
                hits.add(v["vendor_id"])
    return hits.pop() if len(hits) == 1 else None


@dataclass
class Candidate:
    bill: Bill
    txn: BankTxn
    reasons_for: list[str] = field(default_factory=list)
    reasons_against: list[str] = field(default_factory=list)
    kind: str = "full"  # full | partial | duplicate
    status: LinkStatus = LinkStatus.CANDIDATE


def _window_ok(bill: Bill, txn: BankTxn) -> bool:
    due = bill.due_date or bill.issue_date
    return bill.issue_date <= txn.posted_on <= due + timedelta(days=LATE_WINDOW_DAYS)


def _open_balance_at(store: Store, bill: Bill, on: date, paid: dict[str, Decimal]) -> Decimal:
    credited = sum((c.amount for c in store.credits(bill.bill_id) if c.issued_on <= on), Decimal("0"))
    return bill.total - credited - paid.get(bill.bill_id, Decimal("0"))


def candidates_for_txn(store: Store, txn: BankTxn, paid: dict[str, Decimal]) -> list[Candidate]:
    """Bills this debit could pay, given what each bill has already been paid (`paid`)."""
    if txn.amount >= 0:
        return []
    amount = -txn.amount
    vendor_id = descriptor_vendor(txn.descriptor, store.vendor_dicts())
    all_bills = store.bills()
    # Any open bill (of any vendor) in currency/date window with remaining balance == amount
    open_same_amount = [
        b for b in all_bills
        if b.currency == txn.currency and _window_ok(b, txn) and _open_balance_at(store, b, txn.posted_on, paid) == amount
    ]
    out: list[Candidate] = []
    for bill in all_bills:
        if vendor_id is None or bill.vendor_id != vendor_id or bill.currency != txn.currency:
            continue
        if not _window_ok(bill, txn):
            continue
        open_balance = _open_balance_at(store, bill, txn.posted_on, paid)
        reasons = [f"descriptor '{txn.descriptor}' matches vendor {store.vendor_name(bill.vendor_id)}",
                   f"posted {txn.posted_on} within issue date to due date + {LATE_WINDOW_DAYS} days"]
        has_inv_no = bill.invoice_number.lower() in txn.descriptor.lower()
        if has_inv_no:
            reasons.append("descriptor contains the invoice number")
        if open_balance > 0 and amount == open_balance:
            other_open = [b.invoice_number for b in open_same_amount if b.bill_id != bill.bill_id]
            if has_inv_no or not other_open:
                extra = [] if has_inv_no else ["no other open bill of any vendor has this amount"]
                out.append(Candidate(
                    bill, txn, reasons + [f"amount {amount} equals open balance"] + extra,
                    kind="full", status=LinkStatus.CONFIRMED,
                ))
            else:
                out.append(Candidate(
                    bill, txn, reasons + [f"amount {amount} equals open balance"],
                    [f"other open bill(s) also have open balance {amount}: {', '.join(other_open)}"],
                    kind="full", status=LinkStatus.CANDIDATE,
                ))
        elif open_balance > 0 and amount < open_balance:
            status = LinkStatus.CONFIRMED if has_inv_no else LinkStatus.CANDIDATE
            against = ["would leave a balance"] if has_inv_no else [
                "partial payment without invoice number in descriptor (not confirmed)",
                "would leave a balance",
            ]
            out.append(Candidate(
                bill, txn, reasons + [f"amount {amount} is less than open balance {open_balance}"],
                against, kind="partial", status=status,
            ))
        elif open_balance <= 0 and amount == bill.total:
            status = LinkStatus.CONFIRMED if has_inv_no else LinkStatus.CANDIDATE
            out.append(Candidate(
                bill, txn, reasons + [f"amount {amount} equals the bill total"],
                ["bill is already paid: possible duplicate payment (not confirmed)"],
                kind="duplicate", status=status,
            ))
    return out


def link_payments(store: Store) -> list[PaymentLink]:
    """Create payment links for the extracted-records database, oldest debit first.

    A link is CONFIRMED only when the bank descriptor contains the bill's invoice
    number, or the amount equals exactly one open bill's remaining balance for the
    vendor named in the descriptor and no other open bill of any vendor has that
    amount. A partial payment, a duplicate of an already-paid total, or any other
    inferred link is recorded as CANDIDATE with reasons explaining why, and does
    not reduce the confirmed open balance.
    """
    paid: dict[str, Decimal] = {}
    links: list[PaymentLink] = []
    for txn in store.txns():
        cands = candidates_for_txn(store, txn, paid)
        if not cands:
            continue
        pick = None
        # Strongest evidence first: invoice number in the descriptor, then an exact
        # open-balance match, then an exact repeat of a paid bill's total, then a
        # partial payment.
        for level in (
            [c for c in cands if c.bill.invoice_number.lower() in txn.descriptor.lower()],
            [c for c in cands if c.kind == "full"],
            [c for c in cands if c.kind == "duplicate"],
            [c for c in cands if c.kind == "partial"],
        ):
            if len(level) == 1:
                pick = level[0]
                break
            if len(level) > 1:
                # Ambiguous at the strongest level: record each as CANDIDATE with reason
                amount = -txn.amount
                peers = ", ".join(c.bill.invoice_number for c in level)
                for c in level:
                    links.append(PaymentLink(
                        business_id=store.business_id, bill_id=c.bill.bill_id, txn_id=txn.txn_id,
                        amount_applied=amount, status=LinkStatus.CANDIDATE,
                        reasons=c.reasons_for + c.reasons_against + [f"ambiguous among bills: {peers}"],
                    ))
                break
        if pick is None:
            continue
        amount = -txn.amount
        if pick.status is LinkStatus.CONFIRMED:
            paid[pick.bill.bill_id] = paid.get(pick.bill.bill_id, Decimal("0")) + amount
        links.append(PaymentLink(
            business_id=store.business_id, bill_id=pick.bill.bill_id, txn_id=txn.txn_id,
            amount_applied=amount, status=pick.status,
            reasons=pick.reasons_for + pick.reasons_against,
        ))
    return links
