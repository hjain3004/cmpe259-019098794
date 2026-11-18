"""Parse the date formats vendors print.

Numeric dates are never read in a guessed order. A date such as 05/03/2026 means
May 3 in the US and 5 March in most other places, so the caller passes the order
the document uses (`"MDY"` or `"DMY"`, from the business or vendor record). When
only one reading is a real date (25/12/2018), that reading is used whatever the
order. When both readings are real and no order is known, AmbiguousDateError is
raised so the caller can flag the value instead of storing a wrong date.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

DateOrder = Literal["MDY", "DMY"]

_TEXT_FORMATS = (
    "%b %d %Y", "%B %d %Y",            # Aug 13 2026 (commas removed first)
    "%d %b %Y", "%d %B %Y",            # 13 Aug 2026
    "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y", "%d/%b/%y", "%d %b %y",
)
_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_COMPACT = re.compile(r"^\d{8}$")
_TIME = re.compile(r"\s+\d{1,2}:\d{2}(:\d{2})?\s*([AaPp]\.?[Mm]\.?)?$")
_NUMERIC = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$")


class DateParseError(ValueError):
    pass


class AmbiguousDateError(DateParseError):
    """Both month-first and day-first readings are valid and no order was given."""


def _make(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text: str, order: DateOrder | None = None) -> date:
    s = re.sub(r"\s+", " ", text.strip().rstrip("."))
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)  # "Aug 13th, 2026"
    s = s.replace("Sept ", "Sep ").replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = _TIME.sub("", s).strip()  # receipts print the time after the date: "29/12/2017 11:41"

    m = _ISO.match(s)
    if m:
        got = _make(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if got:
            return got
        raise DateParseError(f"invalid date {text!r}")
    m = _COMPACT.match(s)
    if m:  # 8 digits: 20180304 (year first) or 25032018 (day or month first)
        ymd = _make(int(s[:4]), int(s[4:6]), int(s[6:]))
        if ymd and 1900 <= ymd.year <= 2100:
            return ymd
        s = f"{s[:2]}/{s[2:4]}/{s[4:]}"

    m = _NUMERIC.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        mdy, dmy = _make(y, a, b), _make(y, b, a)
        if mdy and dmy and mdy != dmy:
            if order is None:
                raise AmbiguousDateError(f"ambiguous date {text!r}: month-first or day-first?")
            return mdy if order == "MDY" else dmy
        if mdy or dmy:
            return mdy or dmy  # only one reading is a real date
        raise DateParseError(f"invalid date {text!r}")

    for fmt in _TEXT_FORMATS:
        try:
            return datetime.strptime(s.title() if "%b" in fmt or "%B" in fmt else s, fmt).date()
        except ValueError:
            continue
    raise DateParseError(f"unrecognized date {text!r}")
