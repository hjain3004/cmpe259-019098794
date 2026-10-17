"""What the extraction LLM returns.

The extraction model sees one document and one schema, nothing else (no tools,
no database, no conversation). It returns raw strings plus the exact quote each
value came from. Code then (1) checks the quote appears verbatim on the stated
page, (2) attaches character offsets, and (3) normalizes money, dates and terms.
The model never produces Decimals, ISO dates or derived due dates itself.

Header and line items are separate calls, so a long item list cannot make the
header extraction fragile.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .common import Strict


class Extracted(Strict):
    """One extracted value and the verbatim text it was read from."""

    value: str | None = Field(None, description="Value as printed, or null if absent.")
    source_quote: str | None = Field(
        None, description="Exact text copied from the document that contains the value."
    )
    page: int | None = Field(None, ge=1, description="1-based page of source_quote.")

    @model_validator(mode="after")
    def _quote_required(self) -> "Extracted":
        if self.value is not None and not (self.source_quote and self.page):
            raise ValueError("a non-null value needs a source_quote and a page")
        return self


class InvoiceHeaderExtraction(Strict):
    """Call 1 per invoice: a shallow header (14 fields, no nesting beyond Extracted)."""

    vendor_name: Extracted
    invoice_number: Extracted
    issue_date: Extracted
    stated_due_date: Extracted
    payment_terms_raw: Extracted = Field(description='e.g. "Net 30", "Due on receipt", "EOM".')
    currency: Extracted
    subtotal: Extracted
    tax: Extracted
    total: Extracted
    remit_bank_name: Extracted
    remit_account: Extracted
    remit_routing: Extracted
    reference_or_po: Extracted
    memo: Extracted


class LineItem(Strict):
    description: str
    quantity: str | None = None
    unit: str | None = None
    unit_price: str | None = None
    line_total: str | None = None
    source_quote: str = Field(description="The full printed line this item was read from.")
    page: int = Field(ge=1)


class LineItemsExtraction(Strict):
    """Call 2 per invoice."""

    items: list[LineItem]


class MessageKind(str, Enum):
    CORRECTION = "correction"
    PAYMENT_CLAIM = "payment_claim"
    BANK_CHANGE_REQUEST = "bank_change_request"
    REMINDER = "reminder"
    OTHER = "other"


class MessageClaimExtraction(Strict):
    """One call per vendor email or text: what the message asserts, not whether it is true."""

    kind: MessageKind
    invoice_refs: list[str] = Field(default_factory=list)
    claimed_amount: Extracted
    claimed_date: Extracted
    new_remit_bank_name: Extracted
    new_remit_account: Extracted
    new_remit_routing: Extracted
    summary_quote: str = Field(description="The one sentence that best states the claim, verbatim.")
