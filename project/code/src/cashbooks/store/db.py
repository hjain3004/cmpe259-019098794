"""SQLite storage. One file per bundle.

Money is stored as TEXT decimal strings and dates as ISO TEXT, so nothing
passes through a float. Every table carries business_id, and every read goes
through `Store`, which is bound to one business_id by application code.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from cashbooks.contracts.records import (
    BankTxn, Bill, BillLine, Credit, Document, EvidenceSpan, MessageClaim,
    PaymentLink, Vendor, VendorAlias, VendorFingerprint,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors (
  business_id TEXT NOT NULL, vendor_id TEXT NOT NULL, canonical_name TEXT NOT NULL,
  PRIMARY KEY (business_id, vendor_id));
CREATE TABLE IF NOT EXISTS vendor_aliases (
  business_id TEXT NOT NULL, vendor_id TEXT NOT NULL, alias TEXT NOT NULL, verified INTEGER NOT NULL,
  PRIMARY KEY (business_id, vendor_id, alias));
CREATE TABLE IF NOT EXISTS vendor_fingerprints (
  business_id TEXT NOT NULL, vendor_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
  account_hash TEXT NOT NULL, account_last4 TEXT NOT NULL,
  routing_hash TEXT, routing_last4 TEXT, bank_name TEXT,
  verified_on TEXT NOT NULL, trusted_contact TEXT);
CREATE TABLE IF NOT EXISTS documents (
  business_id TEXT NOT NULL, doc_id TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL,
  received_on TEXT NOT NULL, extraction_complete INTEGER NOT NULL,
  PRIMARY KEY (business_id, doc_id));
CREATE TABLE IF NOT EXISTS evidence_spans (
  business_id TEXT NOT NULL, span_id TEXT NOT NULL, doc_id TEXT NOT NULL,
  page INTEGER NOT NULL, start INTEGER NOT NULL, "end" INTEGER NOT NULL, quote TEXT NOT NULL,
  PRIMARY KEY (business_id, span_id));
CREATE TABLE IF NOT EXISTS bills (
  business_id TEXT NOT NULL, bill_id TEXT NOT NULL, vendor_id TEXT, doc_id TEXT NOT NULL,
  invoice_number TEXT NOT NULL, printed_vendor_name TEXT,
  issue_date TEXT NOT NULL, stated_due_date TEXT, payment_terms_raw TEXT,
  terms_kind TEXT NOT NULL, net_days INTEGER, due_date_derived TEXT, due_date_calculation TEXT,
  currency TEXT NOT NULL, subtotal TEXT, tax TEXT, total TEXT NOT NULL,
  remit_account_hash TEXT, remit_account_last4 TEXT,
  remit_routing_hash TEXT, remit_routing_last4 TEXT, remit_bank_name TEXT,
  field_evidence TEXT NOT NULL, ungrounded_fields TEXT NOT NULL,
  PRIMARY KEY (business_id, bill_id));
CREATE TABLE IF NOT EXISTS bill_lines (
  business_id TEXT NOT NULL, bill_id TEXT NOT NULL, line_no INTEGER NOT NULL,
  description TEXT NOT NULL, quantity TEXT, unit TEXT, unit_price TEXT, line_total TEXT,
  evidence_id TEXT NOT NULL,
  PRIMARY KEY (business_id, bill_id, line_no));
CREATE TABLE IF NOT EXISTS message_claims (
  business_id TEXT NOT NULL, claim_id TEXT NOT NULL, doc_id TEXT NOT NULL, kind TEXT NOT NULL,
  invoice_refs TEXT NOT NULL, claimed_amount TEXT, claimed_date TEXT,
  new_account_hash TEXT, new_account_last4 TEXT, evidence_id TEXT NOT NULL,
  PRIMARY KEY (business_id, claim_id));
CREATE TABLE IF NOT EXISTS bank_txns (
  business_id TEXT NOT NULL, txn_id TEXT NOT NULL, posted_on TEXT NOT NULL,
  amount TEXT NOT NULL, currency TEXT NOT NULL, descriptor TEXT NOT NULL,
  PRIMARY KEY (business_id, txn_id));
CREATE TABLE IF NOT EXISTS credits (
  business_id TEXT NOT NULL, credit_id TEXT NOT NULL, bill_id TEXT NOT NULL,
  amount TEXT NOT NULL, issued_on TEXT NOT NULL, evidence_id TEXT NOT NULL,
  PRIMARY KEY (business_id, credit_id));
CREATE TABLE IF NOT EXISTS payment_links (
  business_id TEXT NOT NULL, bill_id TEXT NOT NULL, txn_id TEXT NOT NULL,
  amount_applied TEXT NOT NULL, status TEXT NOT NULL, reasons TEXT NOT NULL,
  PRIMARY KEY (business_id, bill_id, txn_id));
"""

_TABLES: dict[type[BaseModel], str] = {
    Vendor: "vendors", VendorAlias: "vendor_aliases", VendorFingerprint: "vendor_fingerprints",
    Document: "documents", EvidenceSpan: "evidence_spans", Bill: "bills", BillLine: "bill_lines",
    MessageClaim: "message_claims", BankTxn: "bank_txns", Credit: "credits", PaymentLink: "payment_links",
}

_JSON_COLUMNS = {"field_evidence", "ungrounded_fields", "invoice_refs", "reasons"}


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _to_sql(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    if hasattr(value, "value"):  # Enum
        return value.value
    return value


def insert(conn: sqlite3.Connection, records: Iterable[BaseModel]) -> int:
    n = 0
    for rec in records:
        table = _TABLES[type(rec)]
        data = {}
        for k, v in rec.model_dump().items():
            data[k] = json.dumps(v) if k in _JSON_COLUMNS else _to_sql(v)
        cols = ", ".join(f'"{c}"' for c in data)
        marks = ", ".join("?" for _ in data)
        conn.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", list(data.values()))
        n += 1
    conn.commit()
    return n


def _row(model: type[BaseModel], row: sqlite3.Row) -> BaseModel:
    data = dict(row)
    for k in _JSON_COLUMNS & data.keys():
        data[k] = json.loads(data[k])
    return model.model_validate(data)


class Store:
    """Read access for one business. The model never chooses business_id."""

    def __init__(self, conn: sqlite3.Connection, business_id: str):
        self.conn = conn
        self.business_id = business_id

    def _all(self, model: type[BaseModel], where: str = "", params: tuple = (), order: str = "") -> list:
        table = _TABLES[model]
        sql = f"SELECT * FROM {table} WHERE business_id = ?"
        if where:
            sql += f" AND ({where})"
        if order:
            sql += f" ORDER BY {order}"
        return [_row(model, r) for r in self.conn.execute(sql, (self.business_id, *params))]

    # vendors
    def vendors(self) -> list[Vendor]:
        return self._all(Vendor, order="vendor_id")

    def aliases(self) -> list[VendorAlias]:
        return self._all(VendorAlias, order="vendor_id, alias")

    def vendor_dicts(self) -> list[dict]:
        """Vendors in the shape normalize.vendors.resolve_vendor expects."""
        aliases = self.aliases()
        return [
            {"vendor_id": v.vendor_id, "canonical_name": v.canonical_name,
             "aliases": [{"alias": a.alias, "verified": a.verified} for a in aliases if a.vendor_id == v.vendor_id]}
            for v in self.vendors()
        ]

    def vendor_name(self, vendor_id: str | None) -> str:
        if vendor_id is None:
            return "unknown vendor"
        rows = self._all(Vendor, "vendor_id = ?", (vendor_id,))
        return rows[0].canonical_name if rows else vendor_id

    def fingerprints(self, vendor_id: str) -> list[VendorFingerprint]:
        return self._all(VendorFingerprint, "vendor_id = ?", (vendor_id,), "verified_on DESC")

    # bills
    def bills(self) -> list[Bill]:
        return self._all(Bill, order="issue_date, invoice_number")

    def bill(self, bill_id: str) -> Bill | None:
        rows = self._all(Bill, "bill_id = ?", (bill_id,))
        return rows[0] if rows else None

    def bills_by_invoice_number(self, invoice_number: str) -> list[Bill]:
        return self._all(Bill, "UPPER(invoice_number) = UPPER(?)", (invoice_number.strip(),))

    def lines(self, bill_id: str) -> list[BillLine]:
        return self._all(BillLine, "bill_id = ?", (bill_id,), "line_no")

    # money movement
    def links(self, bill_id: str) -> list[PaymentLink]:
        return self._all(PaymentLink, "bill_id = ?", (bill_id,), "txn_id")

    def txn(self, txn_id: str) -> BankTxn | None:
        rows = self._all(BankTxn, "txn_id = ?", (txn_id,))
        return rows[0] if rows else None

    def txns(self) -> list[BankTxn]:
        return self._all(BankTxn, order="posted_on, txn_id")

    def credits(self, bill_id: str) -> list[Credit]:
        return self._all(Credit, "bill_id = ?", (bill_id,), "issued_on")

    # messages and evidence
    def claims(self) -> list[MessageClaim]:
        return self._all(MessageClaim, order="claim_id")

    def span(self, span_id: str) -> EvidenceSpan | None:
        rows = self._all(EvidenceSpan, "span_id = ?", (span_id,))
        return rows[0] if rows else None

    def evidence_ids(self) -> set[str]:
        """Every citable ID for this business: spans, bank rows, vendor-history entries."""
        ids = {r[0] for r in self.conn.execute("SELECT span_id FROM evidence_spans WHERE business_id = ?", (self.business_id,))}
        ids |= {r[0] for r in self.conn.execute("SELECT txn_id FROM bank_txns WHERE business_id = ?", (self.business_id,))}
        ids |= {r[0] for r in self.conn.execute("SELECT evidence_id FROM vendor_fingerprints WHERE business_id = ?", (self.business_id,))}
        return ids
