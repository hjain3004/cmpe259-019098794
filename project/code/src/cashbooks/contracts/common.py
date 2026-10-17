"""Shared types used by every contract.

Money is always a Decimal with an explicit currency and is serialized as a
string, so no amount ever passes through a float.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

Currency = Literal["USD", "EUR"]

# Two decimal places, serialized as a string ("842.00"), never as a float.
Amount = Annotated[
    Decimal,
    Field(max_digits=12, decimal_places=2),
    PlainSerializer(lambda d: f"{d:.2f}", return_type=str, when_used="json"),
]

# Evidence IDs name the record a claim rests on:
#   span_*  a verified quote inside a document (invoice field, message sentence)
#   txn_*   a bank-statement row
#   vh_*    an entry in the owner's trusted vendor history
EvidenceId = Annotated[str, StringConstraints(pattern=r"^(span|txn|vh)_[A-Za-z0-9_-]+$")]

Last4 = Annotated[str, StringConstraints(pattern=r"^\d{4}$")]


class Strict(BaseModel):
    """Base for every contract: unknown keys are errors, not silently dropped."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Money(Strict):
    amount: Amount
    currency: Currency


class Answerability(str, Enum):
    ANSWER = "ANSWER"      # the evidence settles the question
    CLARIFY = "CLARIFY"    # one missing slot (vendor, invoice, date) blocks the answer
    ABSTAIN = "ABSTAIN"    # the records cannot settle it, or the request is out of scope
    WARN = "WARN"          # answerable, but a payment-risk indicator must be shown first


class PaymentState(str, Enum):
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    OVERPAID = "overpaid"


class MaskedAccount(Strict):
    """Payment details as the model is allowed to see them: never full numbers."""

    bank_name: str | None = None
    account_last4: Last4 | None = None
    routing_last4: Last4 | None = None
