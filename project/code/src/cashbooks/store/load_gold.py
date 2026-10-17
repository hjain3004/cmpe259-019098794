"""Load a bundle's gold records (the ledger) into SQLite.

This is the C4 (oracle) database and the reference that extraction is scored
against. Values come from ledger.json; evidence comes from the rendered
documents, so every gold field still points at the exact text on the page.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from cashbooks.contracts.records import (
    BankTxn, Bill, BillLine, Credit, Document, DocumentKind, EvidenceSpan, LinkStatus,
    MessageClaim, PaymentLink, Vendor, VendorAlias, VendorFingerprint,
)
from cashbooks.ingest.bank_csv import read_bank_csv
from cashbooks.ingest.bundle import read_fields_manifest, read_ledger, read_messages
from cashbooks.ingest.pdf_text import find_span, page_texts
from cashbooks.normalize.fingerprint import fingerprint, mask_digits
from cashbooks.normalize.terms import derive_due_date, parse_terms
from cashbooks.store.db import Store, connect, insert

_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _id(*parts: str) -> str:
    return "_".join(_SAFE.sub("-", p) for p in parts)


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _m(s: str | None) -> Decimal | None:
    return Decimal(s).quantize(Decimal("0.01")) if s is not None else None


class LoadReport:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ungrounded: list[str] = []

    def add(self, name: str, n: int) -> None:
        self.counts[name] = self.counts.get(name, 0) + n

    def __str__(self) -> str:
        parts = ", ".join(f"{k}={v}" for k, v in self.counts.items())
        tail = f"; ungrounded: {', '.join(self.ungrounded)}" if self.ungrounded else ""
        return parts + tail


def _spans_from_manifest(business_id: str, doc_id: str, pdf: Path, manifest: dict, report: LoadReport):
    """Turn the renderer's field manifest into verified evidence spans."""
    pages = page_texts(pdf)
    spans: dict[str, EvidenceSpan] = {}
    ungrounded: list[str] = []

    def locate(key: str, text: str, page: int) -> None:
        hit = find_span(pages[page - 1], text) if 0 < page <= len(pages) else None
        if hit is None:
            ungrounded.append(key)
            report.ungrounded.append(f"{doc_id}:{key}")
            return
        start, end, exact = hit
        spans[key] = EvidenceSpan(
            business_id=business_id, span_id=_id("span", doc_id, key), doc_id=doc_id,
            page=page, start=start, end=end, quote=mask_digits(exact),
        )

    for key, f in manifest.get("fields", {}).items():
        locate(key, f["text"], f.get("page", 1))
    for i, line in enumerate(manifest.get("lines", []), start=1):
        locate(f"line{i}", line["text"], line.get("page", 1))
    return spans, ungrounded


def load_gold(bundle_dir: str | Path, conn: sqlite3.Connection | None = None) -> tuple[Store, LoadReport]:
    bundle = Path(bundle_dir)
    ledger = read_ledger(bundle)
    biz = ledger["business"]["business_id"]
    conn = conn or connect()
    report = LoadReport()
    records: list = []

    # ---- trusted vendor history
    vh_doc = Document(business_id=biz, doc_id="vendor_history", kind=DocumentKind.VENDOR_HISTORY,
                      path="vendor_history.json", received_on=date.fromisoformat(ledger["business"]["evaluation_clock"]))
    records.append(vh_doc)
    for v in ledger["vendors"]:
        records.append(Vendor(business_id=biz, vendor_id=v["vendor_id"], canonical_name=v["canonical_name"]))
        for a in v.get("aliases", []):
            records.append(VendorAlias(business_id=biz, vendor_id=v["vendor_id"], alias=a["alias"], verified=a["verified"]))
        vp = v.get("verified_payment")
        if vp:
            acct_hash, acct4 = fingerprint(vp["account_number"])
            r_hash, r4 = fingerprint(vp["routing_number"]) if vp.get("routing_number") else (None, None)
            records.append(VendorFingerprint(
                business_id=biz, vendor_id=v["vendor_id"], evidence_id=_id("vh", v["vendor_id"]),
                account_hash=acct_hash, account_last4=acct4, routing_hash=r_hash, routing_last4=r4,
                bank_name=vp.get("bank_name"), verified_on=date.fromisoformat(vp["verified_on"]),
                trusted_contact=v.get("trusted_contact"),
            ))

    # ---- invoices
    bill_ids: dict[str, str] = {}
    for inv in ledger["invoices"]:
        num = inv["invoice_number"]
        pdf = bundle / "invoices" / f"{num}.pdf"
        manifest = read_fields_manifest(pdf)
        doc_id = manifest.get("doc_id", _id("inv", num))
        bill_id = _id("bill", num)
        bill_ids[num] = bill_id
        issue = date.fromisoformat(inv["issue_date"])
        records.append(Document(business_id=biz, doc_id=doc_id, kind=DocumentKind.INVOICE,
                                path=str(pdf.relative_to(bundle)), received_on=issue))
        spans, ungrounded = _spans_from_manifest(biz, doc_id, pdf, manifest, report)
        records.extend(spans.values())

        terms = parse_terms(inv.get("payment_terms"))
        derived, calc = derive_due_date(issue, terms)
        if inv.get("stated_due_date"):
            stated = date.fromisoformat(inv["stated_due_date"])
        elif inv.get("print_due_date"):
            stated = derived
        else:
            stated = None
        remit = inv.get("remit") or {}
        a_hash, a4 = fingerprint(remit["account_number"]) if remit.get("account_number") else (None, None)
        r_hash, r4 = fingerprint(remit["routing_number"]) if remit.get("routing_number") else (None, None)
        records.append(Bill(
            business_id=biz, bill_id=bill_id, vendor_id=inv["vendor_id"], doc_id=doc_id,
            invoice_number=num, printed_vendor_name=inv.get("printed_vendor_name"),
            issue_date=issue, stated_due_date=stated, payment_terms_raw=inv.get("payment_terms"),
            terms_kind=terms.kind, net_days=terms.net_days, due_date_derived=derived,
            due_date_calculation=calc, currency=inv["currency"],
            subtotal=_m(inv.get("subtotal")), tax=_m(inv.get("tax")), total=_m(inv["total"]),
            remit_account_hash=a_hash, remit_account_last4=a4,
            remit_routing_hash=r_hash, remit_routing_last4=r4, remit_bank_name=remit.get("bank_name"),
            field_evidence={k: s.span_id for k, s in spans.items() if not k.startswith("line")},
            ungrounded_fields=ungrounded,
        ))
        for i, line in enumerate(inv.get("lines", []), start=1):
            span = spans.get(f"line{i}")
            records.append(BillLine(
                business_id=biz, bill_id=bill_id, line_no=i, description=line["description"],
                quantity=_m(line.get("quantity")), unit=line.get("unit"),
                unit_price=_m(line.get("unit_price")), line_total=_m(line.get("line_total")),
                evidence_id=span.span_id if span else _id("span", doc_id, "total"),
            ))
        report.add("invoices", 1)

    # ---- credit notes
    for cr in ledger.get("credits", []):
        pdf = bundle / "credits" / f"{cr['credit_id']}.pdf"
        doc_id = _id("cn", cr["credit_id"])
        evidence = _id("span", doc_id, "total")
        if pdf.exists():
            manifest = read_fields_manifest(pdf)
            doc_id = manifest.get("doc_id", doc_id)
            records.append(Document(business_id=biz, doc_id=doc_id, kind=DocumentKind.CREDIT_NOTE,
                                    path=str(pdf.relative_to(bundle)), received_on=date.fromisoformat(cr["issued_on"])))
            spans, _ = _spans_from_manifest(biz, doc_id, pdf, manifest, report)
            records.extend(spans.values())
            for key in ("total", "amount", "credit_amount"):
                if key in spans:
                    evidence = spans[key].span_id
                    break
        records.append(Credit(business_id=biz, credit_id=cr["credit_id"], bill_id=bill_ids[cr["invoice_number"]],
                              amount=_m(cr["amount"]), issued_on=date.fromisoformat(cr["issued_on"]), evidence_id=evidence))
        report.add("credits", 1)

    # ---- bank rows (read from the CSV, as a real system would)
    for row in read_bank_csv(bundle / "bank.csv"):
        records.append(BankTxn(business_id=biz, **row))
        report.add("bank_rows", 1)

    # ---- gold payment links
    for p in ledger.get("payments", []):
        records.append(PaymentLink(
            business_id=biz, bill_id=bill_ids[p["invoice_number"]], txn_id=p["txn_id"],
            amount_applied=_m(p["amount_applied"]), status=LinkStatus.CONFIRMED, reasons=["gold ledger link"],
        ))
        report.add("payment_links", 1)

    # ---- messages: the body is the document; claims come from the ledger
    bodies = {m["msg_id"]: m for m in read_messages(bundle / "messages.jsonl")}
    for m in ledger.get("messages", []):
        mid = m["msg_id"]
        doc_id = _id("msg", mid)
        body = bodies.get(mid, m)["body"]
        records.append(Document(business_id=biz, doc_id=doc_id, kind=DocumentKind.MESSAGE,
                                path="messages.jsonl", received_on=date.fromisoformat(m["received_on"])))
        span_id = _id("span", "msg", mid)
        records.append(EvidenceSpan(business_id=biz, span_id=span_id, doc_id=doc_id, page=1,
                                    start=0, end=len(body), quote=mask_digits(body)))
        new_hash = new4 = None
        if m.get("kind") == "bank_change_request":
            digits = re.findall(r"\b\d{6,}\b", body)
            if digits:
                new_hash, new4 = fingerprint(max(digits, key=len))
        records.append(MessageClaim(
            business_id=biz, claim_id=_id("claim", mid), doc_id=doc_id, kind=m.get("kind", "other"),
            invoice_refs=m.get("invoice_refs", []), new_account_hash=new_hash, new_account_last4=new4,
            evidence_id=span_id,
        ))
        report.add("messages", 1)

    insert(conn, records)
    return Store(conn, biz), report


if __name__ == "__main__":
    import sys

    path = Path(sys.argv[1])
    db = path / "gold.sqlite"
    if db.exists():
        db.unlink()
    store, rep = load_gold(path, connect(db))
    print(f"loaded {store.business_id} into {db}: {rep}")
