"""Read-only tools: match_payments, sum_amount_due, compare_vendor_payment_details,
summarize_purchases and get_source_evidence."""

from __future__ import annotations

import re
from decimal import Decimal

from cashbooks.contracts.common import MaskedAccount, Money, PaymentState
from cashbooks.contracts.tools import (
    CompareVendorPaymentDetailsArgs, CompareVendorPaymentDetailsResult, EvidenceQuote,
    GetSourceEvidenceArgs, GetSourceEvidenceResult, ListOpenBillsArgs, MatchCandidate,
    MatchPaymentsArgs, MatchPaymentsResult, QuantityByUnit, SumAmountDueArgs, SumAmountDueResult,
    SummarizePurchasesArgs, SummarizePurchasesResult,
)
from cashbooks.normalize.fingerprint import mask_digits
from cashbooks.normalize.vendors import resolve_vendor
from cashbooks.store.db import Store
from cashbooks.tools.bills import list_open_bills
from cashbooks.tools.errors import ToolError
from cashbooks.tools.matching import candidates_for_txn
from cashbooks.tools.status import compute_state


def _one_bill(store: Store, invoice_number: str):
    bills = store.bills_by_invoice_number(invoice_number)
    if not bills:
        raise ToolError(f"no bill found for {invoice_number!r}")
    if len(bills) > 1:
        raise ToolError(f"invoice number is ambiguous; matching bill_ids: {', '.join(b.bill_id for b in bills)}")
    return bills[0]


# ---------------------------------------------------------------- match_payments


def match_payments(store: Store, args: MatchPaymentsArgs) -> MatchPaymentsResult:
    if args.invoice_number:
        bill = _one_bill(store, args.invoice_number)
        links = store.links(bill.bill_id)
        if links:
            cands = []
            for ln in links:
                txn = store.txn(ln.txn_id)
                cands.append(MatchCandidate(
                    bill_id=bill.bill_id, invoice_number=bill.invoice_number, txn_id=txn.txn_id,
                    txn_amount=Money(amount=txn.amount, currency=txn.currency),
                    reasons_for=list(ln.reasons) + [f"posted {txn.posted_on}, descriptor '{txn.descriptor}'"],
                    evidence_ids=[txn.txn_id],
                ))
            note = None
            if len(cands) > 1:
                total = sum((-c.txn_amount.amount for c in cands), Decimal("0"))
                note = f"{len(cands)} payments totalling {total} against a bill total of {bill.total}"
            return MatchPaymentsResult(outcome="confirmed", candidates=cands, why_undecided=note)
        # No link yet: look for debits that could pay it.
        cands = []
        for txn in store.txns():
            for c in candidates_for_txn(store, txn, {}):
                if c.bill.bill_id == bill.bill_id:
                    cands.append(_cand(c))
        return _result(cands)

    if args.txn_id:
        txn = store.txn(args.txn_id)
        if txn is None:
            raise ToolError(f"no bank transaction {args.txn_id!r}")
        return _for_txn(store, txn)

    # Lookup by amount and/or date.
    hits = [t for t in store.txns()
            if (args.amount is None or -t.amount == args.amount)
            and (args.posted_on is None or t.posted_on == args.posted_on)]
    if not hits:
        return MatchPaymentsResult(outcome="no_candidates", candidates=[],
                                   why_undecided="no bank debit with that amount/date")
    cands: list[MatchCandidate] = []
    for t in hits[:5]:
        r = _for_txn(store, t)
        cands.extend(r.candidates or [MatchCandidate(
            bill_id=None, invoice_number=None, txn_id=t.txn_id,
            txn_amount=Money(amount=t.amount, currency=t.currency),
            reasons_for=[f"bank debit posted {t.posted_on}, descriptor '{t.descriptor}'"],
            reasons_against=["no bill from a known vendor matches this transaction"],
            evidence_ids=[t.txn_id])])
    linked = [c for c in cands if c.bill_id]
    if len(cands) == 1 and linked:
        return MatchPaymentsResult(outcome="confirmed", candidates=cands)
    if not linked:
        return MatchPaymentsResult(outcome="ambiguous" if len(cands) > 1 else "no_candidates",
                                   candidates=cands if len(cands) > 1 else [],
                                   why_undecided="; ".join(f"{c.txn_id}: {c.reasons_against[0]}" for c in cands)
                                   if len(cands) > 1 else f"{cands[0].txn_id} ({cands[0].reasons_for[0]}): no bill matches")
    return MatchPaymentsResult(outcome="ambiguous", candidates=cands,
                               why_undecided="more than one transaction or bill fits")


def _cand(c) -> MatchCandidate:
    return MatchCandidate(
        bill_id=c.bill.bill_id, invoice_number=c.bill.invoice_number, txn_id=c.txn.txn_id,
        txn_amount=Money(amount=c.txn.amount, currency=c.txn.currency),
        reasons_for=c.reasons_for, reasons_against=c.reasons_against, evidence_ids=[c.txn.txn_id],
    )


def _result(cands: list[MatchCandidate]) -> MatchPaymentsResult:
    if not cands:
        return MatchPaymentsResult(outcome="no_candidates", candidates=[])
    if len(cands) == 1:
        return MatchPaymentsResult(outcome="confirmed", candidates=cands)
    return MatchPaymentsResult(outcome="ambiguous", candidates=cands,
                               why_undecided="several transactions or bills fit equally well")


def _for_txn(store: Store, txn) -> MatchPaymentsResult:
    linked = [b for b in store.bills() if any(l.txn_id == txn.txn_id for l in store.links(b.bill_id))]
    if linked:
        cands = []
        for b in linked:
            ln = next(l for l in store.links(b.bill_id) if l.txn_id == txn.txn_id)
            cands.append(MatchCandidate(
                bill_id=b.bill_id, invoice_number=b.invoice_number, txn_id=txn.txn_id,
                txn_amount=Money(amount=txn.amount, currency=txn.currency),
                reasons_for=list(ln.reasons) + [f"posted {txn.posted_on}, descriptor '{txn.descriptor}'"],
                evidence_ids=[txn.txn_id] + [e for e in (b.field_evidence.get("total"), b.field_evidence.get("invoice_number")) if e],
            ))
        return MatchPaymentsResult(outcome="confirmed", candidates=cands)
    if txn.amount >= 0:
        return MatchPaymentsResult(outcome="no_candidates", candidates=[],
                                   why_undecided=f"{txn.txn_id} is a deposit, not a payment")
    return _result([_cand(c) for c in candidates_for_txn(store, txn, {})])


# ---------------------------------------------------------------- sum_amount_due


def sum_amount_due(store: Store, args: SumAmountDueArgs) -> SumAmountDueResult:
    r = list_open_bills(store, ListOpenBillsArgs(as_of=args.as_of, vendor=args.vendor))
    bills = [b for b in r.bills if b.overdue] if args.overdue_only else r.bills
    totals: dict[str, Decimal] = {}
    for b in bills:
        totals[b.remaining.currency] = totals.get(b.remaining.currency, Decimal("0")) + b.remaining.amount
    return SumAmountDueResult(
        as_of=args.as_of,
        totals=[Money(amount=v, currency=k) for k, v in sorted(totals.items())],
        contributing_bills=bills,
    )


# ---------------------------------------------------------------- compare_vendor_payment_details


def compare_vendor_payment_details(store: Store, args: CompareVendorPaymentDetailsArgs) -> CompareVendorPaymentDetailsResult:
    bill = _one_bill(store, args.invoice_number)
    on_doc = MaskedAccount(bank_name=bill.remit_bank_name, account_last4=bill.remit_account_last4,
                           routing_last4=bill.remit_routing_last4)
    doc_ev = [bill.field_evidence[k] for k in ("remit_bank_name", "remit_account", "remit_routing") if k in bill.field_evidence]
    fps = store.fingerprints(bill.vendor_id) if bill.vendor_id else []
    if not fps:
        return CompareVendorPaymentDetailsResult(outcome="no_history", on_document=on_doc, on_file=None,
                                                 document_evidence=doc_ev)
    fp = fps[0]
    on_file = MaskedAccount(bank_name=fp.bank_name, account_last4=fp.account_last4, routing_last4=fp.routing_last4)
    diffs = []
    if bill.remit_account_hash and bill.remit_account_hash != fp.account_hash:
        diffs.append(f"account number differs: invoice ends {bill.remit_account_last4}, record on file ends {fp.account_last4}")
    if bill.remit_routing_hash and fp.routing_hash and bill.remit_routing_hash != fp.routing_hash:
        diffs.append(f"routing number differs: invoice ends {bill.remit_routing_last4}, record on file ends {fp.routing_last4}")
    if bill.remit_bank_name and fp.bank_name and bill.remit_bank_name.strip().lower() != fp.bank_name.strip().lower():
        diffs.append(f"bank differs: invoice says {bill.remit_bank_name}, record on file says {fp.bank_name}")
    return CompareVendorPaymentDetailsResult(
        outcome="changed" if diffs else "same", on_document=on_doc, on_file=on_file, differences=diffs,
        trusted_contact=fp.trusted_contact, document_evidence=doc_ev, history_evidence=[fp.evidence_id],
    )


# ---------------------------------------------------------------- summarize_purchases

_STOP = {"of", "the", "a", "an", "and", "for", "in", "on"}


def _tokens(item: str) -> list[str]:
    toks = [t for t in re.findall(r"[a-z0-9]+", item.lower()) if t not in _STOP]
    return [t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks]


def summarize_purchases(store: Store, args: SummarizePurchasesArgs) -> SummarizePurchasesResult:
    vendor_ids = None
    if args.vendor:
        vendor_ids = {c.vendor_id for c in resolve_vendor(args.vendor, store.vendor_dicts())}
        if not vendor_ids:
            raise ToolError(f"no known vendor matches {args.vendor!r}")
    toks = _tokens(args.item)
    qty: dict[str, Decimal] = {}
    spend: dict[str, Decimal] = {}
    evidence, n = [], 0
    for bill in store.bills():
        if not (args.date_from <= bill.issue_date <= args.date_to):
            continue
        if vendor_ids is not None and bill.vendor_id not in vendor_ids:
            continue
        vname = store.vendor_name(bill.vendor_id).lower()
        for ln in store.lines(bill.bill_id):
            text = f"{ln.description} {ln.unit or ''} {vname}".lower()
            if toks and all(t in text for t in toks):
                n += 1
                unit = ln.unit or "unit"
                qty[unit] = qty.get(unit, Decimal("0")) + (ln.quantity or Decimal("0"))
                if ln.line_total is not None:
                    spend[bill.currency] = spend.get(bill.currency, Decimal("0")) + ln.line_total
                evidence.append(ln.evidence_id)
    return SummarizePurchasesResult(
        matched_lines=n,
        quantities=[QuantityByUnit(unit=u, quantity=q) for u, q in sorted(qty.items())],
        spend=[Money(amount=v, currency=k) for k, v in sorted(spend.items())],
        evidence_ids=evidence,
    )


# ---------------------------------------------------------------- get_source_evidence


def get_source_evidence(store: Store, args: GetSourceEvidenceArgs) -> GetSourceEvidenceResult:
    quotes, missing = [], []
    docs = {r["doc_id"]: r for r in store.conn.execute(
        "SELECT doc_id, kind, path FROM documents WHERE business_id = ?", (store.business_id,))}
    for eid in args.evidence_ids:
        if eid.startswith("span_"):
            sp = store.span(eid)
            if sp is None:
                missing.append(eid)
                continue
            d = docs.get(sp.doc_id)
            label = sp.doc_id.split("_", 1)[-1]
            kind = d["kind"] if d else "document"
            source = f"{kind.replace('_', ' ')} {label}, page {sp.page}" if kind != "message" else f"message {label}"
            quotes.append(EvidenceQuote(evidence_id=eid, source=source, quote=sp.quote))
        elif eid.startswith("txn_"):
            t = store.txn(eid)
            if t is None:
                missing.append(eid)
                continue
            quotes.append(EvidenceQuote(evidence_id=eid, source=f"bank statement row {t.posted_on}",
                                        quote=f"{t.posted_on} | {t.descriptor} | {t.amount:.2f} {t.currency}"))
        elif eid.startswith("vh_"):
            vid = eid[3:]
            fps = store.fingerprints(vid)
            if not fps:
                missing.append(eid)
                continue
            fp = fps[0]
            aliases = [a.alias for a in store.aliases() if a.vendor_id == vid and a.verified]
            quote = (f"{store.vendor_name(vid)}; verified aliases: {', '.join(aliases) or 'none'}; "
                     f"bank {fp.bank_name}, account ending {fp.account_last4}, routing ending {fp.routing_last4}; "
                     f"verified {fp.verified_on}; contact on file: {fp.trusted_contact}")
            quotes.append(EvidenceQuote(evidence_id=eid, source="owner's trusted vendor record", quote=quote))
        else:
            missing.append(eid)
    quotes = [EvidenceQuote(evidence_id=q.evidence_id, source=q.source, quote=mask_digits(q.quote)) for q in quotes]
    return GetSourceEvidenceResult(quotes=quotes, missing=missing)
