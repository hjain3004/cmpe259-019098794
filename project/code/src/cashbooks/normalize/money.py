"""Turn printed amounts into Decimal with an explicit currency."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from cashbooks.contracts.common import Money

_SYMBOLS = {"$": "USD", "US$": "USD", "€": "EUR"}
_CODES = {"USD", "EUR"}
_AMOUNT = re.compile(r"-?\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|-?\(?\d+(?:\.\d+)?\)?")  # comma-grouped, or plain digits


class MoneyParseError(ValueError):
    pass


def parse_amount(text: str) -> Decimal:
    """'$1,118.25' -> Decimal('1118.25'); '(45.00)' -> Decimal('-45.00')."""
    m = _AMOUNT.search(text.replace(" ", ""))
    if not m:
        raise MoneyParseError(f"no amount in {text!r}")
    raw = m.group()
    negative = (
        raw.startswith("-")
        or (raw.startswith("(") and raw.endswith(")"))
        or re.search(r"-\s*(?:US)?[$€]\s*\d", text) is not None
        or re.search(r"\(\s*(?:US)?[$€]\s*[\d,.]+\s*\)", text) is not None
    )
    digits = raw.strip("-()").replace(",", "")
    try:
        value = Decimal(digits).quantize(Decimal("0.01"))
    except InvalidOperation as e:
        raise MoneyParseError(f"bad amount {text!r}") from e
    return -value if negative else value


def detect_currency(text: str, default: str | None = None) -> str | None:
    upper = text.upper()
    for code in _CODES:
        if re.search(rf"\b{code}\b", upper):
            return code
    for sym, code in sorted(_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        if sym in text:
            return code
    return default


def parse_money(text: str, default_currency: str | None = None) -> Money:
    currency = detect_currency(text, default_currency)
    if currency is None:
        raise MoneyParseError(f"no currency in {text!r} and no default given")
    return Money(amount=parse_amount(text), currency=currency)
