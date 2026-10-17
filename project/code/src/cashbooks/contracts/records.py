"""Normalized records stored in SQLite, after code has verified and normalized
the extraction output. One model per table in the design doc.

Every row carries business_id. Application code sets it; the model never does.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import Field, model_validator

from .common import Amount, Currency, EvidenceId, Last4, Strict


class DocumentKind(str, Enum):
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"
    MESSAGE = "message"
    BANK_STATEMENT = "bank_statement"
    VENDOR_HISTORY = "vendor_history"


class Vendor(Strict):
    business_id: str
    vendor_id: str
    canonical_name: str


class VendorAlias(Strict):
    business_id: str
    vendor_id: str
    alias: str
    verified: bool


class VendorFingerprint(Strict):
    """Owner-verified payment details. Stored as a keyed hash plus last four digits."""

    business_id: str
    vendor_id: str
    evidence_id: EvidenceId  # vh_*
    account_hash: str
    account_last4: Last4
    routing_hash: str | None = None
    routing_last4: Last4 | None = None
    bank_name: str | None = None
    verified_on: date
    trusted_contact: str | None = None


class Document(Strict):
    business_id: str
    doc_id: str
    kind: DocumentKind
    path: str
    received_on: date
    extraction_complete: bool = True  # False for empty/corrupted/locked files (S10)


class EvidenceSpan(Strict):
    business_id: str
    span_id: EvidenceId
    doc_id: str
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int
    quote: str

    @model_validator(mode="after")
    def _offsets_match_quote(self) -> "EvidenceSpan":
        if self.end - self.start != len(self.quote):
            raise ValueError("end - start must equal len(quote)")
        return self


class TermsKind(str, Enum):
    NET = "net"
    EOM = "eom"
    DUE_ON_RECEIPT = "due_on_receipt"
    UNKNOWN = "unknown"


class Bill(Strict):
    business_id: str
    bill_id: str
    vendor_id: str | None  # None when the vendor could not be linked
    doc_id: str
    invoice_number: str
    printed_vendor_name: str | None = None
    issue_date: date
    stated_due_date: date | None = None
    payment_terms_raw: str | None = None
    terms_kind: TermsKind = TermsKind.UNKNOWN
    net_days: int | None = Field(None, ge=0)
    due_date_derived: date | None = None
    due_date_calculation: str | None = None  # e.g. "2026-08-15 + 30 days (Net 30)"
    currency: str  # validated against Currency on load; kept str so S10 cases can store "?"
    subtotal: Amount | None = None
    tax: Amount | None = None
    total: Amount
    remit_account_hash: str | None = None
    remit_account_last4: Last4 | None = None
    remit_routing_hash: str | None = None
    remit_routing_last4: Last4 | None = None
    remit_bank_name: str | None = None
    field_evidence: dict[str, EvidenceId] = Field(default_factory=dict)
    ungrounded_fields: list[str] = Field(default_factory=list)  # never cited

    @property
    def due_date(self) -> date | None:
        """The printed due date if there is one, otherwise the date derived from the terms."""
        return self.stated_due_date or self.due_date_derived

    @property
    def due_date_conflict(self) -> bool:
        return (
            self.stated_due_date is not None
            and self.due_date_derived is not None
            and self.stated_due_date != self.due_date_derived
        )


class BillLine(Strict):
    business_id: str
    bill_id: str
    line_no: int = Field(ge=1)
    description: str
    quantity: Amount | None = None
    unit: str | None = None
    unit_price: Amount | None = None
    line_total: Amount | None = None
    evidence_id: EvidenceId


class MessageClaim(Strict):
    business_id: str
    claim_id: str
    doc_id: str
    kind: str
    invoice_refs: list[str] = Field(default_factory=list)
    claimed_amount: Amount | None = None
    claimed_date: date | None = None
    new_account_hash: str | None = None
    new_account_last4: Last4 | None = None
    evidence_id: EvidenceId


class BankTxn(Strict):
    business_id: str
    txn_id: EvidenceId  # txn_*
    posted_on: date
    amount: Amount  # signed: debits negative
    currency: Currency
    descriptor: str


class Credit(Strict):
    business_id: str
    credit_id: str
    bill_id: str
    amount: Amount = Field(gt=0)
    issued_on: date
    evidence_id: EvidenceId


class LinkStatus(str, Enum):
    CONFIRMED = "confirmed"
    CANDIDATE = "candidate"


class PaymentLink(Strict):
    business_id: str
    bill_id: str
    txn_id: EvidenceId
    amount_applied: Amount = Field(gt=0)
    status: LinkStatus
    reasons: list[str] = Field(min_length=1)
