"""Parse a bank-statement CSV with plain code. No model touches bank data."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED = ("txn_id", "posted_on", "amount", "currency", "descriptor")


class BankCsvError(ValueError):
    pass


def read_bank_csv(path: str | Path) -> list[dict]:
    """Return rows with txn_id, posted_on (date), amount (Decimal, signed), currency, descriptor."""
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise BankCsvError(f"missing columns: {missing}")
        for n, r in enumerate(reader, start=2):
            try:
                amount = Decimal(r["amount"].replace(",", "").strip())
                posted = date.fromisoformat(r["posted_on"].strip())
            except (InvalidOperation, ValueError) as e:
                raise BankCsvError(f"line {n}: {e}") from e
            rows.append(
                {
                    "txn_id": r["txn_id"].strip(),
                    "posted_on": posted,
                    "amount": amount.quantize(Decimal("0.01")),
                    "currency": r["currency"].strip().upper(),
                    "descriptor": r["descriptor"].strip(),
                }
            )
    ids = [r["txn_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise BankCsvError("duplicate txn_id")
    return rows
