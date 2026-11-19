"""Render a scenario bundle's documents from its ledger.

    python data/generator/render.py data/dev/cafe_01

Reads <bundle>/ledger.json and writes, into the same folder:
  invoices/<number>.pdf + .fields.json   text-native invoices, one layout per vendor
  credits/<id>.pdf + .fields.json        credit notes
  messages.jsonl                         vendor emails and texts (no labels)
  bank.csv                               txn_id,posted_on,amount,currency,descriptor
  vendor_history.json                    the owner's trusted vendor record

Each .fields.json records exactly what was printed for every field, as it reads
back from the PDF, so gold evidence can point at real text. The script checks
the ledger's arithmetic and that every recorded field can be found in the PDF,
and exits non-zero if anything is off.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pdfplumber
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

WS = re.compile(r"\s+")


def collapse(s: str) -> str:
    return WS.sub(" ", s).strip()


def money(s: str, currency: str = "USD") -> str:
    sym = "€" if currency == "EUR" else "$"
    return f"{sym}{Decimal(s):,.2f}"


DATE_FORMATS = {"northside": "%m/%d/%Y", "greenway": "%b %d, %Y", "beanworks": "%Y-%m-%d"}


def fmt_date(iso: str, template: str) -> str:
    return date.fromisoformat(iso).strftime(DATE_FORMATS.get(template, "%Y-%m-%d"))


def due_date(inv: dict) -> str:
    if inv.get("stated_due_date"):
        return inv["stated_due_date"]
    days = int(re.search(r"\d+", inv["payment_terms"]).group())
    return (date.fromisoformat(inv["issue_date"]) + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------- validation


class LedgerError(ValueError):
    pass


def validate_ledger(ledger: dict) -> None:
    errs = []
    for inv in ledger["invoices"]:
        n = inv["invoice_number"]
        planted = inv.get("planted") or {}
        sub = Decimal("0")
        for ln in inv["lines"]:
            if Decimal(ln["quantity"]) * Decimal(ln["unit_price"]) != Decimal(ln["line_total"]):
                errs.append(f"{n}: line '{ln['description']}' quantity x price != line_total")
            sub += Decimal(ln["line_total"])
        if sub != Decimal(inv["subtotal"]) and not planted.get("stated_total_mismatch"):
            errs.append(f"{n}: lines sum {sub} != subtotal {inv['subtotal']}")
        if Decimal(inv["subtotal"]) + Decimal(inv["tax"]) != Decimal(inv["total"]) and not planted.get("stated_total_mismatch"):
            errs.append(f"{n}: subtotal + tax != total")
        if inv.get("stated_due_date") and not planted.get("due_date_conflict"):
            days = int(re.search(r"\d+", inv["payment_terms"]).group())
            derived = (date.fromisoformat(inv["issue_date"]) + timedelta(days=days)).isoformat()
            if inv["stated_due_date"] != derived:
                errs.append(f"{n}: stated_due_date {inv['stated_due_date']} != derived {derived}")
    txns = {t["txn_id"]: t for t in ledger["bank"]}
    if len(txns) != len(ledger["bank"]):
        errs.append("duplicate txn_id in bank")
    applied: dict[str, Decimal] = {}
    for p in ledger.get("payments", []):
        if p["txn_id"] not in txns:
            errs.append(f"payment references unknown {p['txn_id']}")
            continue
        applied[p["txn_id"]] = applied.get(p["txn_id"], Decimal("0")) + Decimal(p["amount_applied"])
    for tid, amt in applied.items():
        if Decimal(txns[tid]["amount"]) != -amt:
            errs.append(f"{tid}: amount {txns[tid]['amount']} != -(applied {amt})")
    numbers = {i["invoice_number"] for i in ledger["invoices"]}
    for c in ledger.get("credits", []):
        if c["invoice_number"] not in numbers:
            errs.append(f"credit {c['credit_id']} references unknown invoice")
    if errs:
        raise LedgerError("\n".join(errs))


# ---------------------------------------------------------------- layouts


class Page:
    """Small helper over a reportlab canvas that remembers what it printed."""

    def __init__(self, path: Path):
        self.c = canvas.Canvas(str(path), pagesize=letter)
        self.fields: dict[str, str] = {}
        self.line_texts: list[str] = []

    def text(self, x, y, s, size=10, bold=False, field=None, value=None):
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawString(x, y, s)
        if field:
            self.fields[field] = value if value is not None else s

    def right(self, x, y, s, size=10, bold=False, field=None, value=None):
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawRightString(x, y, s)
        if field:
            self.fields[field] = value if value is not None else s

    def rule(self, y):
        self.c.setLineWidth(0.5)
        self.c.line(54, y, 558, y)

    def save(self):
        self.c.save()


def line_rows(p: Page, inv: dict, y: float, cols: tuple[int, int, int, int]) -> float:
    """Print item rows: description, quantity + unit, unit price, line total."""
    xd, xq, xp, xt = cols
    cur = inv.get("currency", "USD")
    for ln in inv["lines"]:
        p.text(xd, y, ln["description"])
        p.right(xq, y, f"{ln['quantity']} {ln['unit']}")
        p.right(xp, y, money(ln["unit_price"], cur))
        p.right(xt, y, money(ln["line_total"], cur))
        p.line_texts.append(ln["description"])
        y -= 16
    return y


def remit_block(p: Page, inv: dict, y: float, x: float = 54) -> float:
    r = inv["remit"]
    p.text(x, y, "Remit payment to:", bold=True)
    p.text(x, y - 14, f"Bank: {r['bank_name']}", field="remit_bank_name", value=r["bank_name"])
    p.text(x, y - 28, f"Account: {r['account_number']}", field="remit_account", value=r["account_number"])
    p.text(x, y - 42, f"Routing: {r['routing_number']}", field="remit_routing", value=r["routing_number"])
    return y - 60


def _draw_memo(p: Page, inv: dict, y: float, label: str = "Memo:") -> None:
    if not inv.get("memo"):
        return
    words, line, rows = inv["memo"].split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > 95:
            rows.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    rows.append(line)
    p.text(54, y, label, bold=True)
    for i, row in enumerate(rows):
        p.text(54, y - 14 - 12 * i, row, size=9)
    p.fields["memo"] = inv["memo"]


def layout_northside(p: Page, inv: dict, vendor: dict, biz: dict) -> None:
    t = "northside"
    cur = inv.get("currency", "USD")
    p.text(54, 740, inv["printed_vendor_name"], size=18, bold=True, field="vendor_name")
    p.text(54, 724, "1450 Harbor Way, Oakland, CA 94607  |  (415) 555-0142")
    p.text(420, 740, "INVOICE", size=16, bold=True)
    p.text(420, 720, f"Invoice No: {inv['invoice_number']}", field="invoice_number", value=inv["invoice_number"])
    issue = fmt_date(inv["issue_date"], t)
    p.text(420, 706, f"Invoice Date: {issue}", field="issue_date", value=issue)
    if inv["print_due_date"]:
        due = fmt_date(due_date(inv), t)
        p.text(420, 692, f"Due Date: {due}", field="stated_due_date", value=due)
    p.text(420, 678, f"Terms: {inv['payment_terms']}", field="payment_terms", value=inv["payment_terms"])
    if inv.get("reference_or_po"):
        p.text(420, 664, f"PO: {inv['reference_or_po']}", field="reference_or_po", value=inv["reference_or_po"])
    p.text(54, 690, "Bill to:", bold=True)
    p.text(54, 676, biz["name"])
    p.text(54, 662, "88 Alder Street, San Jose, CA 95112")
    p.rule(640)
    p.text(54, 626, "Description", bold=True)
    p.right(380, 626, "Qty", bold=True)
    p.right(470, 626, "Unit price", bold=True)
    p.right(558, 626, "Amount", bold=True)
    p.rule(618)
    y = line_rows(p, inv, 602, (54, 380, 470, 558))
    p.rule(y + 6)
    y -= 10
    p.right(470, y, "Subtotal")
    p.right(558, y, money(inv["subtotal"], cur), field="subtotal")
    p.right(470, y - 16, "Sales tax")
    p.right(558, y - 16, money(inv["tax"], cur), field="tax")
    p.right(470, y - 34, f"Total Due ({cur})", bold=True)
    p.right(558, y - 34, money(inv["total"], cur), bold=True, field="total")
    p.fields["currency"] = cur
    y = remit_block(p, inv, y - 80)
    _draw_memo(p, inv, y, label="Note:")


def layout_greenway(p: Page, inv: dict, vendor: dict, biz: dict) -> None:
    t = "greenway"
    cur = inv.get("currency", "USD")
    p.text(54, 742, inv["printed_vendor_name"], size=20, bold=True, field="vendor_name")
    p.text(54, 726, "Fresh produce, delivered daily  |  Hayward, CA  |  (510) 555-0187", size=9)
    p.rule(712)
    p.text(54, 694, f"Invoice # {inv['invoice_number']}", size=12, bold=True, field="invoice_number", value=inv["invoice_number"])
    issue = fmt_date(inv["issue_date"], t)
    p.text(54, 678, f"Date: {issue}", field="issue_date", value=issue)
    p.text(54, 664, f"Payment terms: {inv['payment_terms']}", field="payment_terms", value=inv["payment_terms"])
    if inv.get("print_due_date"):
        due = fmt_date(due_date(inv), t)
        p.text(54, 650, f"Due date: {due}", field="stated_due_date", value=due)
    if inv.get("reference_or_po"):
        p.text(330, 664, f"Ref: {inv['reference_or_po']}", field="reference_or_po", value=inv["reference_or_po"])
    p.text(330, 694, "Customer:", bold=True)
    p.text(330, 680, biz["name"])
    p.text(54, 632, "Item", bold=True)
    p.right(360, 632, "Quantity", bold=True)
    p.right(460, 632, "Price", bold=True)
    p.right(558, 632, "Total", bold=True)
    p.rule(624)
    y = line_rows(p, inv, 608, (54, 360, 460, 558))
    p.rule(y + 6)
    y -= 12
    p.right(460, y, "Invoice total", bold=True)
    p.right(558, y, money(inv["total"], cur), bold=True, field="total")
    y = remit_block(p, inv, y - 50)
    _draw_memo(p, inv, y, label="Note:")


def layout_beanworks(p: Page, inv: dict, vendor: dict, biz: dict) -> None:
    t = "beanworks"
    cur = inv.get("currency", "USD")
    p.text(54, 742, "TAX INVOICE", size=10, bold=True)
    p.text(54, 722, inv["printed_vendor_name"], size=16, bold=True, field="vendor_name")
    p.text(54, 708, "Small-batch roasters  |  2210 Third St, San Francisco, CA", size=9)
    issue = fmt_date(inv["issue_date"], t)
    p.text(360, 742, f"Number: {inv['invoice_number']}", field="invoice_number", value=inv["invoice_number"])
    p.text(360, 728, f"Issued: {issue}", field="issue_date", value=issue)
    if inv["print_due_date"]:
        due = fmt_date(due_date(inv), t)
        p.text(360, 714, f"Due: {due}", field="stated_due_date", value=due)
    p.text(360, 700, f"Terms: {inv['payment_terms']}", field="payment_terms", value=inv["payment_terms"])
    if inv.get("reference_or_po"):
        p.text(360, 686, f"Ref: {inv['reference_or_po']}", field="reference_or_po", value=inv["reference_or_po"])
    p.text(54, 680, f"Sold to: {biz['name']}")
    p.rule(664)
    p.text(54, 650, "Product", bold=True)
    p.right(390, 650, "Qty", bold=True)
    p.right(480, 650, "Each", bold=True)
    p.right(558, 650, "Line total", bold=True)
    p.rule(642)
    y = line_rows(p, inv, 626, (54, 390, 480, 558))
    p.rule(y + 6)
    y -= 12
    p.right(480, y, "Subtotal")
    p.right(558, y, money(inv["subtotal"], cur), field="subtotal")
    p.right(480, y - 16, "Tax")
    p.right(558, y - 16, money(inv["tax"], cur), field="tax")
    p.right(480, y - 34, f"Amount due {cur}", bold=True)
    p.right(558, y - 34, money(inv["total"], cur), bold=True, field="total")
    p.fields["currency"] = cur
    y = remit_block(p, inv, y - 80)
    _draw_memo(p, inv, y, label="Memo:")


LAYOUTS = {"northside": layout_northside, "greenway": layout_greenway, "beanworks": layout_beanworks}


def render_credit(path: Path, cr: dict, vendor: dict, biz: dict) -> Page:
    p = Page(path)
    p.text(54, 740, vendor["canonical_name"], size=18, bold=True, field="vendor_name")
    p.text(400, 740, "CREDIT NOTE", size=14, bold=True)
    p.text(400, 722, f"Credit No: {cr['credit_id']}", field="credit_id", value=cr["credit_id"])
    p.text(400, 708, f"Date: {fmt_date(cr['issued_on'], vendor['template'])}", field="issue_date",
           value=fmt_date(cr["issued_on"], vendor["template"]))
    p.text(54, 690, f"Customer: {biz['name']}")
    p.text(54, 660, f"Applies to invoice: {cr['invoice_number']}", field="invoice_ref", value=cr["invoice_number"])
    p.text(54, 646, f"Reason: {cr['reason']}")
    p.text(54, 620, f"Credit amount: {money(cr['amount'])}", bold=True, field="total", value=money(cr["amount"]))
    p.save()
    return p


# ---------------------------------------------------------------- manifest


def manifest(pdf: Path, p: Page, doc_id: str) -> dict:
    """Record each field's printed text as it reads back from the PDF, and check it is there."""
    with pdfplumber.open(str(pdf)) as d:
        pages = [pg.extract_text() or "" for pg in d.pages]
    flat = collapse(pages[0])
    fields, missing = {}, []
    for k, v in p.fields.items():
        if collapse(v) in flat:
            fields[k] = {"text": collapse(v), "page": 1}
        else:
            missing.append(k)
    lines = []
    for desc in p.line_texts:
        row = next((collapse(l) for l in pages[0].splitlines() if collapse(l).startswith(desc)), None)
        if row is None:
            missing.append(f"line:{desc}")
        else:
            lines.append({"text": row, "page": 1})
    if missing:
        raise LedgerError(f"{pdf.name}: printed text not found on page: {missing}")
    return {"doc_id": doc_id, "fields": fields, "lines": lines}


# ---------------------------------------------------------------- main


def render_bundle(bundle: Path) -> list[str]:
    ledger = json.loads((bundle / "ledger.json").read_text())
    validate_ledger(ledger)
    biz = ledger["business"]
    vendors = {v["vendor_id"]: v for v in ledger["vendors"]}
    out = []
    (bundle / "invoices").mkdir(exist_ok=True)
    (bundle / "credits").mkdir(exist_ok=True)
    for inv in ledger["invoices"]:
        v = vendors[inv["vendor_id"]]
        pdf = bundle / "invoices" / f"{inv['invoice_number']}.pdf"
        mf_path = pdf.with_suffix(".fields.json")
        old_mf = mf_path.read_text() if mf_path.exists() else None
        old_pdf = pdf.read_bytes() if pdf.exists() else None
        p = Page(pdf)
        LAYOUTS[v["template"]](p, inv, v, biz)
        p.save()
        m = manifest(pdf, p, f"inv_{inv['invoice_number']}")
        new_mf = json.dumps(m, indent=2) + "\n"
        mf_path.write_text(new_mf)
        if old_mf == new_mf and old_pdf is not None:
            pdf.write_bytes(old_pdf)
        out.append(f"invoice {inv['invoice_number']:8} {v['template']:9} {len(m['fields'])} fields, {len(m['lines'])} lines")
    for cr in ledger.get("credits", []):
        inv = next(i for i in ledger["invoices"] if i["invoice_number"] == cr["invoice_number"])
        pdf = bundle / "credits" / f"{cr['credit_id']}.pdf"
        mf_path = pdf.with_suffix(".fields.json")
        old_mf = mf_path.read_text() if mf_path.exists() else None
        old_pdf = pdf.read_bytes() if pdf.exists() else None
        p = render_credit(pdf, cr, vendors[inv["vendor_id"]], biz)
        m = manifest(pdf, p, f"cn_{cr['credit_id']}")
        new_mf = json.dumps(m, indent=2) + "\n"
        mf_path.write_text(new_mf)
        if old_mf == new_mf and old_pdf is not None:
            pdf.write_bytes(old_pdf)
        out.append(f"credit  {cr['credit_id']:8} {len(m['fields'])} fields")
    with open(bundle / "messages.jsonl", "w", encoding="utf-8") as f:
        for msg in ledger.get("messages", []):
            f.write(json.dumps({k: msg[k] for k in ("msg_id", "received_on", "channel", "from", "subject", "body")}) + "\n")
    out.append(f"messages {len(ledger.get('messages', []))}")
    with open(bundle / "bank.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["txn_id", "posted_on", "amount", "currency", "descriptor"])
        w.writeheader()
        w.writerows(ledger["bank"])
    out.append(f"bank rows {len(ledger['bank'])}")
    history = [{k: v[k] for k in ("vendor_id", "canonical_name", "aliases", "verified_payment", "trusted_contact")}
               for v in ledger["vendors"]]
    (bundle / "vendor_history.json").write_text(json.dumps(history, indent=2) + "\n")
    out.append(f"vendors {len(history)}")
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        for line in render_bundle(Path(sys.argv[1])):
            print(line)
    except LedgerError as e:
        print(f"FAILED\n{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
