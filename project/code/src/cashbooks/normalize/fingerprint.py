"""Keyed fingerprints for account and routing numbers.

Full numbers are hashed with HMAC-SHA256 and never stored or logged; only the
hash and last four digits are kept. Two documents carrying the same account
produce the same fingerprint, which is all the comparison tool needs.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re

_DEV_KEY = b"cashbooks-dev-key-not-secret"


def _key() -> bytes:
    k = os.environ.get("CASHBOOKS_FP_KEY")
    return k.encode() if k else _DEV_KEY


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def fingerprint(value: str) -> tuple[str, str]:
    """Return (hex digest, last four digits). Raises ValueError if fewer than 4 digits."""
    d = digits_only(value)
    if len(d) < 4:
        raise ValueError("account or routing number has fewer than four digits")
    digest = hmac.new(_key(), d.encode(), hashlib.sha256).hexdigest()
    return digest, d[-4:]


_LONG_DIGITS = re.compile(r"\d{6,}")


def mask_digits(text: str) -> str:
    """Replace every run of 6+ digits with asterisks except its last four.

    Length is preserved, so character offsets into the original text stay valid.
    """
    return _LONG_DIGITS.sub(lambda m: "*" * (len(m.group()) - 4) + m.group()[-4:], text)
