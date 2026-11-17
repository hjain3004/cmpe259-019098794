"""Deterministic payment matching: which bank debit pays which bill.

Used two ways: by match_payments to explain candidates to the model, and by the
extracted-records loader to create payment links (the gold loader takes links
from the ledger instead). Thresholds were set on development bundles only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
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


def _window_ok(bill: Bill, txn: BankTxn) -> bool:
    due = bill.due_date or bill.issue_date
    return bill.issue_date <= txn.posted_on <= due + timedelta(days=LATE_WINDOW_DAYS)


def candidates_for_txn(store: Store, txn: BankTxn, paid: dict[str, Decimal]) -> list[Candidate]:
    """Bills this debit could pay, given what each bill has already been paid (`paid`)."""
    if txn.amount >= 0:
        return []
    amount = -txn.amount
    vendor_id = descriptor_vendor(txn.descriptor, store.vendor_dicts())
    out: list[Candidate] = []
    for bill in store.bills():
        if vendor_id is None or bill.vendor_id != vendor_id or bill.currency != txn.currency:
            continue
        if not _window_ok(bill, txn):
            continue
        credited = sum((c.amount for c in store.credits(bill.bill_id) if c.issued_on <= txn.posted_on), Decimal("0"))
        open_balance = bill.total - credited - paid.get(bill.bill_id, Decimal("0"))
        reasons = [f"descriptor '{txn.descriptor}' matches vendor {store.vendor_name(bill.vendor_id)}",
                   f"posted {txn.posted_on} within issue date to due date + {LATE_WINDOW_DAYS} days"]
        if bill.invoice_number.lower() in txn.descriptor.lower():
            reasons.append("descriptor contains the invoice number")
        if open_balance > 0 and amount == open_balance:
            out.append(Candidate(bill, txn, reasons + [f"amount {amount} equals open balance"], kind="full"))
        elif open_balance > 0 and amount < open_balance:
            out.append(Candidate(bill, txn, reasons + [f"amount {amount} is less than open balance {open_balance}"],
                                 [ "would leave a balance"], kind="partial"))
        elif open_balance <= 0 and amount == bill.total:
            out.append(Candidate(bill, txn, reasons + [f"amount {amount} equals the bill total"],
                                 ["bill is already paid: possible duplicate payment"], kind="duplicate"))
    return out


def link_payments(store: Store) -> list[PaymentLink]:
    """Create payment links for the extracted-records database, oldest debit first.

    Evidence is ranked: the invoice number in the descriptor, then a unique exact
    open-balance match, then a unique exact repeat of an already-paid bill's total
    (linked as a duplicate, so the bill shows as overpaid), then a unique partial
    payment. Ties at the strongest level that fits, and anything else, stay unlinked.
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
        # partial payment. Each level must be unique to be used.
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
                break  # ambiguous at the strongest level that fits: leave unlinked
        if pick is None:
            continue
        amount = -txn.amount
        paid[pick.bill.bill_id] = paid.get(pick.bill.bill_id, Decimal("0")) + amount
        links.append(PaymentLink(
            business_id=store.business_id, bill_id=pick.bill.bill_id, txn_id=txn.txn_id,
            amount_applied=amount, status=LinkStatus.CONFIRMED,
            reasons=pick.reasons_for + pick.reasons_against,
        ))
    return links
