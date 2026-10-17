"""Parse the date formats vendors print. US month-first order is assumed for
numeric dates, because the target users are US businesses."""

from __future__ import annotations

import re
from datetime import date, datetime

_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
)


class DateParseError(ValueError):
    pass


def parse_date(text: str) -> date:
    s = re.sub(r"\s+", " ", text.strip().rstrip("."))
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)  # "Aug 13th, 2026"
    s = s.replace("Sept ", "Sep ")
    for fmt in _FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise DateParseError(f"unrecognized date {text!r}")
