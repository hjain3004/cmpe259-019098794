"""Build a small bundle in the same format the scenario renderer produces,
so store and tool tests run without the full café scenario."""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

VENDORS = [
    {"vendor_id": "v_northside", "canonical_name": "Northside Supplies",
     "aliases": [{"alias": "Northside Supply Co.", "verified": True}],
     "verified_payment": {"bank_name": "Bay Commerce Bank", "account_number": "004417829931",
                          "routing_number": "121000358", "verified_on": "2026-03-02"},
     "trusted_contact": "Dana Ruiz, (415) 555-0142", "template": "northside"},
    {"vendor_id": "v_greenway", "canonical_name": "Greenway Produce", "aliases": [],
     "verified_payment": {"bank_name": "Pacific Western Bank", "account_number": "007733210456",
                          "routing_number": "121042882", "verified_on": "2026-02-11"},
     "trusted_contact": "Miguel Ortega, (510) 555-0187", "template": "greenway"},
]


def _inv(num, vendor, printed, issue, terms, total, print_due, lines):
    vp = next(v for v in VENDORS if v["vendor_id"] == vendor)["verified_payment"]
    return {
        "invoice_number": num, "vendor_id": vendor, "printed_vendor_name": printed,
        "issue_date": issue, "payment_terms": terms, "print_due_date": print_due, "stated_due_date": None,
        "currency": "USD", "lines": lines, "subtotal": total, "tax": "0.00", "total": total,
        "remit": {k: vp[k] for k in ("bank_name", "account_number", "routing_number")},
        "reference_or_po": None, "memo": None, "attack": None,
    }


def _line(desc, qty, unit, price):
    return {"description": desc, "quantity": qty, "unit": unit, "unit_price": price,
            "line_total": f"{Decimal(qty) * Decimal(price):.2f}"}


LEDGER = {
    "business": {"business_id": "mini_01", "name": "Mini Cafe", "type": "cafe", "evaluation_clock": "2026-09-24"},
    "vendors": VENDORS,
    "invoices": [
        _inv("NS-1031", "v_northside", "Northside Supplies", "2026-07-20", "Net 30", "615.40", True,
             [_line("Paper cups 12 oz", "20", "sleeve", "30.77")]),
        _inv("NS-1048", "v_northside", "Northside Supplies", "2026-08-13", "Net 30", "842.00", True,
             [_line("Compostable lids", "40", "sleeve", "21.05")]),
        _inv("NS-1062", "v_northside", "Northside Supplies", "2026-09-01", "Net 30", "1118.25", True,
             [_line("Napkins", "45", "case", "24.85")]),
        _inv("NS-1070", "v_northside", "Northside Supply Co.", "2026-09-02", "Net 30", "389.60", True,
             [_line("Sanitizer", "8", "jug", "48.70")]),
        _inv("GP-221", "v_greenway", "Greenway Produce", "2026-08-05", "Net 15", "268.90", False,
             [_line("Strawberries", "10", "flat", "26.89")]),
        _inv("GP-228", "v_greenway", "Greenway Produce", "2026-08-26", "Net 15", "512.30", False,
             [_line("Avocados", "10", "case", "51.23")]),
    ],
    "credits": [{"credit_id": "CN-0457", "invoice_number": "NS-1062", "amount": "45.00",
                 "issued_on": "2026-09-10", "reason": "damaged lids"}],
    "bank": [
        {"txn_id": "txn_0102", "posted_on": "2026-08-14", "amount": "-615.40", "currency": "USD", "descriptor": "NORTHSIDE SUP CO 8841"},
        {"txn_id": "txn_0109", "posted_on": "2026-08-21", "amount": "-615.40", "currency": "USD", "descriptor": "NORTHSIDE SUP CO 8841"},
        {"txn_id": "txn_0181", "posted_on": "2026-09-09", "amount": "-300.00", "currency": "USD", "descriptor": "GREENWAY PRODUCE ACH"},
        {"txn_id": "txn_0193", "posted_on": "2026-09-12", "amount": "-842.00", "currency": "USD", "descriptor": "NORTHSIDE SUP CO 8841"},
        {"txn_id": "txn_0205", "posted_on": "2026-09-18", "amount": "-1750.00", "currency": "USD", "descriptor": "ONLINE TRANSFER REF 66120"},
    ],
    "payments": [
        {"txn_id": "txn_0102", "invoice_number": "NS-1031", "amount_applied": "615.40"},
        {"txn_id": "txn_0109", "invoice_number": "NS-1031", "amount_applied": "615.40"},
        {"txn_id": "txn_0181", "invoice_number": "GP-228", "amount_applied": "300.00"},
        {"txn_id": "txn_0193", "invoice_number": "NS-1048", "amount_applied": "842.00"},
    ],
    "messages": [
        {"msg_id": "m03", "received_on": "2026-09-15", "channel": "email", "from": "Greenway Produce <ar@greenwayproduce.com>",
         "subject": "Payment received", "body": "Hi! We received your payment for GP-228 in full, thank you!",
         "kind": "payment_claim", "invoice_refs": ["GP-228"]},
        {"msg_id": "m05", "received_on": "2026-09-16", "channel": "email", "from": "Northside <billing@northside.example>",
         "subject": "New bank details", "body": "Please send future payments to account 008812345507 at Summit Digital Bank.",
         "kind": "bank_change_request", "invoice_refs": []},
    ],
}


def _fmt_money(s: str) -> str:
    return f"${Decimal(s):,.2f}"


def _fmt_date(iso: str, template: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%m/%d/%Y") if template == "northside" else d.strftime("%b %d, %Y")


def _render_invoice(inv: dict, path: Path) -> dict:
    vendor = next(v for v in VENDORS if v["vendor_id"] == inv["vendor_id"])
    t = vendor["template"]
    issue = _fmt_date(inv["issue_date"], t)
    net = int(inv["payment_terms"].split()[1])
    due = _fmt_date((date.fromisoformat(inv["issue_date"]) + timedelta(days=net)).isoformat(), t)
    rows = [
        ("vendor_name", inv["printed_vendor_name"], inv["printed_vendor_name"]),
        ("invoice_number", f"Invoice No: {inv['invoice_number']}", inv["invoice_number"]),
        ("issue_date", f"Invoice Date: {issue}", issue),
    ]
    if inv["print_due_date"]:
        rows.append(("stated_due_date", f"Due Date: {due}", due))
    rows += [("payment_terms", f"Terms: {inv['payment_terms']}", inv["payment_terms"])]
    line_rows = []
    for ln in inv["lines"]:
        line_rows.append(f"{ln['description']} {ln['quantity']} {ln['unit']} {_fmt_money(ln['unit_price'])} {_fmt_money(ln['line_total'])}")
    rows += [
        ("subtotal", f"Subtotal: {_fmt_money(inv['subtotal'])}", _fmt_money(inv["subtotal"])),
        ("tax", f"Tax: {_fmt_money(inv['tax'])}", _fmt_money(inv["tax"])),
        ("total", f"Total Due: {_fmt_money(inv['total'])}", _fmt_money(inv["total"])),
        ("remit_bank_name", f"Bank: {inv['remit']['bank_name']}", inv["remit"]["bank_name"]),
        ("remit_account", f"Account: {inv['remit']['account_number']}", inv["remit"]["account_number"]),
        ("remit_routing", f"Routing: {inv['remit']['routing_number']}", inv["remit"]["routing_number"]),
    ]
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 740
    for _, printed, _ in rows[:5]:
        c.drawString(72, y, printed); y -= 18
    for lr in line_rows:
        c.drawString(72, y, lr); y -= 18
    for _, printed, _ in rows[5:]:
        c.drawString(72, y, printed); y -= 18
    c.save()
    return {
        "doc_id": f"inv_{inv['invoice_number']}",
        "fields": {k: {"text": v, "page": 1} for k, _, v in rows},
        "lines": [{"text": lr, "page": 1} for lr in line_rows],
    }


def build(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "invoices").mkdir(exist_ok=True)
    (dest / "credits").mkdir(exist_ok=True)
    (dest / "ledger.json").write_text(json.dumps(LEDGER, indent=2))
    for inv in LEDGER["invoices"]:
        pdf = dest / "invoices" / f"{inv['invoice_number']}.pdf"
        manifest = _render_invoice(inv, pdf)
        pdf.with_suffix(".fields.json").write_text(json.dumps(manifest))
    for cr in LEDGER["credits"]:
        pdf = dest / "credits" / f"{cr['credit_id']}.pdf"
        c = canvas.Canvas(str(pdf), pagesize=letter)
        c.drawString(72, 740, f"Credit Note {cr['credit_id']}")
        c.drawString(72, 722, f"Credit Amount: {_fmt_money(cr['amount'])}")
        c.save()
        pdf.with_suffix(".fields.json").write_text(json.dumps(
            {"doc_id": f"cn_{cr['credit_id']}", "fields": {"total": {"text": _fmt_money(cr["amount"]), "page": 1}}, "lines": []}))
    with open(dest / "bank.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["txn_id", "posted_on", "amount", "currency", "descriptor"])
        w.writeheader()
        w.writerows(LEDGER["bank"])
    with open(dest / "messages.jsonl", "w") as f:
        for m in LEDGER["messages"]:
            f.write(json.dumps({k: m[k] for k in ("msg_id", "received_on", "channel", "from", "subject", "body")}) + "\n")
    (dest / "vendor_history.json").write_text(json.dumps(VENDORS, indent=2))
    return dest
