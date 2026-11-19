"""LLM extraction of a bundle into the records C2 and C3 read.

Per document, one model call per schema (invoice header, line items, credit note,
message claim), each seeing only that document's text. Code then verifies every
quote against the page, normalizes values, resolves vendors against the owner's
trusted record, links bank payments deterministically, and stores the result.
Each call is made once (no retries), so parse failures stay visible in the log.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from cashbooks.contracts.extraction import (
    CreditNoteExtraction, Extracted, InvoiceHeaderExtraction, LineItemsExtraction, MessageClaimExtraction,
)
from cashbooks.contracts.records import (
    BankTxn, Bill, BillLine, Credit, Document, DocumentKind, EvidenceSpan, MessageClaim, Vendor, VendorAlias,
    VendorFingerprint,
)
from cashbooks.ingest.bank_csv import read_bank_csv
from cashbooks.ingest.bundle import read_messages, read_vendor_history
from cashbooks.ingest.pdf_text import find_span, page_texts
from cashbooks.llm.base import LLM, Message, extract_json, simplify_schema
from cashbooks.normalize.dates import AmbiguousDateError, DateParseError, parse_date
from cashbooks.normalize.fingerprint import fingerprint, mask_digits
from cashbooks.normalize.money import MoneyParseError, detect_currency, parse_amount
from cashbooks.normalize.terms import derive_due_date, parse_terms
from cashbooks.normalize.vendors import resolve_vendor
from cashbooks.store.db import Store, connect, insert
from cashbooks.tools.matching import link_payments

PROMPTS = Path(__file__).resolve().parents[4] / "prompts"
_SAFE = re.compile(r"[^A-Za-z0-9_-]")
SPAN_KEY = {"payment_terms_raw": "payment_terms"}
VERBOSE = True  # one progress line per model call


def _id(*parts: str) -> str:
    return "_".join(_SAFE.sub("-", p) for p in parts)


@dataclass
class CallLog:
    doc: str
    schema: str
    ok: bool
    raw: str
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    notes: list[str] = field(default_factory=list)


def _clean(obj: Any) -> Any:
    """Make small, common slips in model output parseable without hiding real errors.

    Empty strings become null. A value with no quote uses the value itself as the
    quote, and a missing page defaults to 1; both are still checked against the
    page text later, so a wrong guess shows up as an ungrounded field.
    """
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if not isinstance(obj, dict):
        if isinstance(obj, str) and obj.strip().lower() in ("", "null", "none"):
            return None
        return obj
    out = {k: _clean(v) for k, v in obj.items()}
    if "value" in out:  # an Extracted field
        if out.get("value") is not None and not out.get("source_quote"):
            out["source_quote"] = out["value"]
        if out.get("value") is not None and not out.get("page"):
            out["page"] = 1
        if out.get("value") is None:
            out["source_quote"], out["page"] = None, None
    elif "description" in out:  # a line item
        if not out.get("source_quote"):
            out["source_quote"] = out.get("description")
        if not out.get("page"):
            out["page"] = 1
    return out


_NULLISH = ("", "null", "none", "n/a")


def _coerce_extracted(model: type[BaseModel], data: Any) -> tuple[Any, list[str]]:
    """A field typed Extracted sometimes comes back as a bare string or null ("memo": "null").
    Wrap it so it validates; the value is still checked against the page like any other."""
    if not isinstance(data, dict):
        return data, []
    changed = []
    for name, f in model.model_fields.items():
        if f.annotation is not Extracted or name not in data:
            continue
        v = data[name]
        if isinstance(v, dict):
            continue
        if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH):
            data[name] = {"value": None, "source_quote": None, "page": None}
        else:
            data[name] = {"value": str(v), "source_quote": str(v), "page": 1}
        changed.append(name)
    return data, changed


def call_schema(llm: LLM, prompt: str, text: str, model: type[BaseModel], doc: str) -> tuple[BaseModel | None, CallLog]:
    if VERBOSE:
        print(f"  extracting {doc} ({model.__name__})", flush=True)
    system = (PROMPTS / prompt).read_text()
    schema = simplify_schema(model.model_json_schema())
    res = llm.complete(system, [Message("user", f"DOCUMENT TEXT\n\n{text}")], json_schema=schema)
    log = CallLog(doc, model.__name__, False, res.text, res.error, res.input_tokens, res.output_tokens, res.latency_ms)
    if res.error:
        return None, log
    data = extract_json(res.text)
    if data is None:
        log.error = "invalid_json"
        return None, log
    data, coerced = _coerce_extracted(model, data)
    if coerced:
        log.notes.append("wrapped bare values: " + ", ".join(coerced))
    try:
        parsed = model.model_validate(_clean(data))
    except ValidationError as e:
        log.error = f"schema_violation: {e.errors()[0]['loc']} {e.errors()[0]['msg']}"
        return None, log
    log.ok = True
    return parsed, log


# ---------------------------------------------------------------- helpers


def _value(f: Extracted | None) -> str | None:
    return f.value.strip() if f is not None and f.value and f.value.strip() else None


def _date(f: Extracted | None, notes: list[str], name: str, order: str | None = None) -> date | None:
    v = _value(f)
    if not v:
        return None
    try:
        return parse_date(v, order)
    except AmbiguousDateError:
        notes.append(f"ambiguous_date:{name}={v!r} (no date order on the vendor or business record)")
        return None
    except DateParseError:
        notes.append(f"unparsed_date:{name}={v!r}")
        return None


def _amount(v: str | None, notes: list[str], name: str) -> Decimal | None:
    if not v:
        return None
    try:
        return abs(parse_amount(v))
    except MoneyParseError:
        notes.append(f"unparsed_amount:{name}={v!r}")
        return None


def _span(biz: str, doc_id: str, key: str, pages: list[str], f: Extracted | None,
          spans: dict, ungrounded: list[str]) -> None:
    if f is None or not f.value:
        return
    page = f.page or 1
    quote = f.source_quote or f.value
    hit = find_span(pages[page - 1], quote) if 0 < page <= len(pages) else None
    if hit is None:  # the quote may be right but on another page
        for i, p in enumerate(pages, start=1):
            hit = find_span(p, quote)
            if hit:
                page = i
                break
    if hit is None:
        ungrounded.append(key)
        return
    s, e, exact = hit
    spans[key] = EvidenceSpan(business_id=biz, span_id=_id("span", doc_id, key), doc_id=doc_id,
                              page=page, start=s, end=e, quote=mask_digits(exact))


# ---------------------------------------------------------------- pipeline


@dataclass
class ExtractionRun:
    store: Store
    calls: list[CallLog]
    extracted: dict  # per document: normalized values, for scoring against the ledger


def extract_bundle(bundle: Path, llm: LLM, db_path: Path | None = None) -> ExtractionRun:
    ledger = json.loads((bundle / "ledger.json").read_text())
    biz = ledger["business"]["business_id"]
    clock = date.fromisoformat(ledger["business"]["evaluation_clock"])
    conn = connect(db_path or ":memory:")
    records: list = []
    calls: list[CallLog] = []
    out: dict = {"invoices": {}, "credits": {}, "messages": {}}

    # Trusted vendor history is the owner's own record: loaded, never extracted.
    history = read_vendor_history(bundle / "vendor_history.json")
    # Numeric dates are read in the order the owner's records give (vendor first, then business); never guessed.
    business_order = ledger["business"].get("date_order")
    vendor_order = {v["vendor_id"]: v.get("date_order") for v in history}
    records.append(Document(business_id=biz, doc_id="vendor_history", kind=DocumentKind.VENDOR_HISTORY,
                            path="vendor_history.json", received_on=clock))
    for v in history:
        records.append(Vendor(business_id=biz, vendor_id=v["vendor_id"], canonical_name=v["canonical_name"]))
        for a in v.get("aliases", []):
            records.append(VendorAlias(business_id=biz, vendor_id=v["vendor_id"], alias=a["alias"], verified=a["verified"]))
        vp = v.get("verified_payment")
        if vp:
            ah, a4 = fingerprint(vp["account_number"])
            rh, r4 = fingerprint(vp["routing_number"]) if vp.get("routing_number") else (None, None)
            records.append(VendorFingerprint(
                business_id=biz, vendor_id=v["vendor_id"], evidence_id=_id("vh", v["vendor_id"]), account_hash=ah,
                account_last4=a4, routing_hash=rh, routing_last4=r4, bank_name=vp.get("bank_name"),
                verified_on=date.fromisoformat(vp["verified_on"]), trusted_contact=v.get("trusted_contact")))

    # Invoices
    bills_by_number: dict[str, str] = {}
    for pdf in sorted((bundle / "invoices").glob("*.pdf")):
        doc_id = _id("inv", pdf.stem)
        pages = page_texts(pdf)
        text = "\n\n".join(f"[page {i}]\n{p}" for i, p in enumerate(pages, start=1))
        head, log = call_schema(llm, "extract_invoice_header_v1.md", text, InvoiceHeaderExtraction, pdf.name)
        calls.append(log)
        items, log2 = call_schema(llm, "extract_line_items_v1.md", text, LineItemsExtraction, pdf.name)
        calls.append(log2)
        if head is None:
            continue
        notes: list[str] = []
        spans: dict = {}
        ungrounded: list[str] = []
        for key in InvoiceHeaderExtraction.model_fields:
            # span keys match the gold loader and the tools ("payment_terms", not the schema's name)
            _span(biz, doc_id, SPAN_KEY.get(key, key), pages, getattr(head, key), spans, ungrounded)
        number = _value(head.invoice_number) or pdf.stem
        cands = resolve_vendor(_value(head.vendor_name) or "", history)
        vendor_id = cands[0].vendor_id if len(cands) == 1 else None
        order = vendor_order.get(vendor_id) or business_order
        issue = _date(head.issue_date, notes, "issue_date", order)
        if issue is None:
            notes.append("no issue date: bill skipped")
            log.notes += notes
            continue
        stated = _date(head.stated_due_date, notes, "stated_due_date", order)
        terms = parse_terms(_value(head.payment_terms_raw))
        derived, calc = derive_due_date(issue, terms)
        total = _amount(_value(head.total), notes, "total")
        if total is None:
            notes.append("no total: bill skipped")
            log.notes += notes
            continue
        if vendor_id is None:
            notes.append(f"vendor unresolved: {_value(head.vendor_name)!r}")
        currency = (_value(head.currency) or "").upper() or detect_currency(_value(head.total) or "", "USD") or "USD"
        acct, rout = _value(head.remit_account), _value(head.remit_routing)
        ah, a4 = fingerprint(acct) if acct and len(re.sub(r"\D", "", acct)) >= 4 else (None, None)
        rh, r4 = fingerprint(rout) if rout and len(re.sub(r"\D", "", rout)) >= 4 else (None, None)
        bill_id = _id("bill", pdf.stem)
        bills_by_number[number.upper()] = bill_id
        records.append(Document(business_id=biz, doc_id=doc_id, kind=DocumentKind.INVOICE,
                                path=str(pdf.relative_to(bundle)), received_on=issue))
        records.extend(spans.values())
        records.append(Bill(
            business_id=biz, bill_id=bill_id, vendor_id=vendor_id, doc_id=doc_id, invoice_number=number,
            printed_vendor_name=_value(head.vendor_name), issue_date=issue, stated_due_date=stated,
            payment_terms_raw=_value(head.payment_terms_raw), terms_kind=terms.kind, net_days=terms.net_days,
            due_date_derived=derived, due_date_calculation=calc, currency=currency[:3],
            subtotal=_amount(_value(head.subtotal), notes, "subtotal"), tax=_amount(_value(head.tax), notes, "tax"),
            total=total, remit_account_hash=ah, remit_account_last4=a4, remit_routing_hash=rh, remit_routing_last4=r4,
            remit_bank_name=_value(head.remit_bank_name),
            field_evidence={k: sp.span_id for k, sp in spans.items()}, ungrounded_fields=ungrounded,
        ))
        lines_out = []
        if items is not None:
            for i, it in enumerate(items.items, start=1):
                key = f"line{i}"
                q = it.source_quote or it.description
                hit = None
                for pno, p in enumerate(pages, start=1):
                    hit = find_span(p, q)
                    if hit:
                        s, e, exact = hit
                        records.append(EvidenceSpan(business_id=biz, span_id=_id("span", doc_id, key), doc_id=doc_id,
                                                    page=pno, start=s, end=e, quote=mask_digits(exact)))
                        break
                ev = _id("span", doc_id, key) if hit else (spans["total"].span_id if "total" in spans else _id("span", doc_id, "total"))
                qty = _amount(re.sub(r"[^\d.,]", "", it.quantity or "") or None, notes, f"{key}.quantity")
                records.append(BillLine(
                    business_id=biz, bill_id=bill_id, line_no=i, description=it.description, quantity=qty,
                    unit=(it.unit or "").strip() or None, unit_price=_amount(it.unit_price, notes, f"{key}.unit_price"),
                    line_total=_amount(it.line_total, notes, f"{key}.line_total"), evidence_id=ev))
                lines_out.append({"description": it.description, "quantity": str(qty) if qty is not None else None,
                                  "line_total": str(_amount(it.line_total, [], "")) if it.line_total else None})
        log.notes += notes
        out["invoices"][pdf.stem] = {
            "invoice_number": number, "vendor_id": vendor_id, "issue_date": issue.isoformat(),
            "stated_due_date": stated.isoformat() if stated else None, "terms": terms.raw,
            "subtotal": str(_amount(_value(head.subtotal), [], "")) if _value(head.subtotal) else None,
            "tax": str(_amount(_value(head.tax), [], "")) if _value(head.tax) else None, "total": str(total),
            "remit_account_last4": a4, "remit_bank_name": _value(head.remit_bank_name), "lines": lines_out,
            "ungrounded": ungrounded,
        }

    # Credit notes
    for pdf in sorted((bundle / "credits").glob("*.pdf")):
        doc_id = _id("cn", pdf.stem)
        pages = page_texts(pdf)
        cn, log = call_schema(llm, "extract_credit_note_v1.md", pages[0], CreditNoteExtraction, pdf.name)
        calls.append(log)
        if cn is None:
            continue
        notes: list[str] = []
        spans, ungrounded = {}, []
        for key, f in (("credit_id", cn.credit_id), ("invoice_ref", cn.invoice_ref), ("issue_date", cn.issue_date),
                       ("total", cn.amount)):
            _span(biz, doc_id, key, pages, f, spans, ungrounded)
        amount = _amount(_value(cn.amount), notes, "amount")
        issued = _date(cn.issue_date, notes, "issue_date", business_order)
        ref = (_value(cn.invoice_ref) or "").upper()
        bill_id = bills_by_number.get(ref)
        log.notes += notes
        out["credits"][pdf.stem] = {"invoice_ref": ref, "amount": str(amount) if amount else None,
                                    "issued_on": issued.isoformat() if issued else None}
        if amount is None or issued is None or bill_id is None:
            log.notes.append("credit skipped: missing amount, date or matching bill")
            continue
        records.append(Document(business_id=biz, doc_id=doc_id, kind=DocumentKind.CREDIT_NOTE,
                                path=str(pdf.relative_to(bundle)), received_on=issued))
        records.extend(spans.values())
        records.append(Credit(business_id=biz, credit_id=_value(cn.credit_id) or pdf.stem, bill_id=bill_id,
                              amount=amount, issued_on=issued, evidence_id=spans["total"].span_id if "total" in spans
                              else _id("span", doc_id, "total")))

    # Bank rows: plain code, no model.
    for row in read_bank_csv(bundle / "bank.csv"):
        records.append(BankTxn(business_id=biz, **row))

    # Messages
    for m in read_messages(bundle / "messages.jsonl"):
        mid = m["msg_id"]
        doc_id = _id("msg", mid)
        body = m["body"]
        text = f"From: {m['from']}\nDate: {m['received_on']}\nSubject: {m.get('subject', '')}\n\n{body}"
        claim, log = call_schema(llm, "extract_message_claim_v1.md", text, MessageClaimExtraction, f"message {mid}")
        calls.append(log)
        records.append(Document(business_id=biz, doc_id=doc_id, kind=DocumentKind.MESSAGE, path="messages.jsonl",
                                received_on=date.fromisoformat(m["received_on"])))
        span_id = _id("span", "msg", mid)
        records.append(EvidenceSpan(business_id=biz, span_id=span_id, doc_id=doc_id, page=1, start=0, end=len(body),
                                    quote=mask_digits(body)))
        if claim is None:
            continue
        notes: list[str] = []
        acct = _value(claim.new_remit_account)
        nh, n4 = fingerprint(acct) if acct and len(re.sub(r"\D", "", acct)) >= 4 else (None, None)
        records.append(MessageClaim(
            business_id=biz, claim_id=_id("claim", mid), doc_id=doc_id, kind=claim.kind.value,
            invoice_refs=[r.strip().upper() for r in claim.invoice_refs if r.strip()],
            claimed_amount=_amount(_value(claim.claimed_amount), notes, "claimed_amount"),
            claimed_date=_date(claim.claimed_date, notes, "claimed_date", business_order),
            new_account_hash=nh, new_account_last4=n4, evidence_id=span_id))
        log.notes += notes
        out["messages"][mid] = {"kind": claim.kind.value, "invoice_refs": sorted(r.strip().upper() for r in claim.invoice_refs),
                                "new_account_last4": n4}

    insert(conn, records)
    store = Store(conn, biz)
    insert(conn, link_payments(store))
    return ExtractionRun(store, calls, out)


# ---------------------------------------------------------------- scoring against the ledger


def score_extraction(bundle: Path, extracted: dict) -> dict:
    """Field-level accuracy of normalized extracted values against the ledger."""
    from collections import Counter

    ledger = json.loads((bundle / "ledger.json").read_text())
    inv_counts = Counter(i["invoice_number"] for i in ledger["invoices"])
    rows = []

    def add(doc, fieldname, gold, got):
        rows.append({"doc": doc, "field": fieldname, "gold": gold, "extracted": got, "correct": gold == got})

    for inv in ledger["invoices"]:
        num = inv["invoice_number"]
        stem = num if inv_counts[num] == 1 else f"{num}--{inv['vendor_id'].removeprefix('v_')}"
        got = extracted["invoices"].get(stem) or extracted["invoices"].get(num)
        due = None
        if inv.get("print_due_date"):
            due = inv.get("stated_due_date") or _ledger_due(inv)
        g = {"invoice_number": num, "vendor_id": inv["vendor_id"], "issue_date": inv["issue_date"],
             "stated_due_date": due, "total": inv["total"], "remit_account_last4": (inv.get("remit") or {}).get("account_number", "")[-4:] or None}
        for k, v in g.items():
            add(num, k, v, got.get(k) if got else None)
        gl = inv["lines"]
        xl = (got or {}).get("lines", [])
        add(num, "line_count", len(gl), len(xl))
        for i, ln in enumerate(gl):
            x = xl[i] if i < len(xl) else {}
            add(num, f"line{i + 1}.line_total", ln["line_total"], x.get("line_total"))
    for cr in ledger.get("credits", []):
        got = extracted["credits"].get(cr["credit_id"]) or {}
        add(cr["credit_id"], "amount", cr["amount"], got.get("amount"))
        add(cr["credit_id"], "invoice_ref", cr["invoice_number"], got.get("invoice_ref"))
    for m in ledger.get("messages", []):
        got = extracted["messages"].get(m["msg_id"]) or {}
        add(m["msg_id"], "kind", m["kind"], got.get("kind"))
        add(m["msg_id"], "invoice_refs", sorted(m["invoice_refs"]), got.get("invoice_refs"))
    correct = sum(r["correct"] for r in rows)
    return {"fields": len(rows), "correct": correct, "accuracy": round(correct / len(rows), 3) if rows else None,
            "errors": [r for r in rows if not r["correct"]]}


def _ledger_due(inv: dict) -> str:
    due, _ = derive_due_date(date.fromisoformat(inv["issue_date"]), parse_terms(inv.get("payment_terms")))
    if due is None:
        raise ValueError(f"cannot derive due date from {inv.get('payment_terms')!r}")
    return due.isoformat()
