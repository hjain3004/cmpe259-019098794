"""Payment-terms parser and due-date derivation.

Handles "Net N", "N days", "Due on receipt", "EOM", and "Net N EOM".
"EOM" means the last day of the issue month; "Net N EOM" means N days after it.
The derived due date is stored separately from any printed due date, with the
calculation spelled out, so conflicts (a printed date that disagrees with the
terms) stay visible instead of being silently resolved.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from cashbooks.contracts.records import TermsKind

_NET = re.compile(r"\bnet\s*(\d{1,3})\b", re.I)
_DAYS = re.compile(r"\b(?:within|in)?\s*(\d{1,3})\s*days?\b", re.I)
_EOM = re.compile(r"\b(eom|end of (?:the )?month)\b", re.I)
_RECEIPT = re.compile(r"\b(due (?:up)?on receipt|payable (?:up)?on receipt|cod|cash on delivery)\b", re.I)


@dataclass(frozen=True)
class Terms:
    kind: TermsKind
    net_days: int | None
    raw: str | None


def parse_terms(raw: str | None) -> Terms:
    if not raw or not raw.strip():
        return Terms(TermsKind.UNKNOWN, None, raw)
    if _RECEIPT.search(raw):
        return Terms(TermsKind.DUE_ON_RECEIPT, 0, raw)
    net = _NET.search(raw) or _DAYS.search(raw)
    days = int(net.group(1)) if net else None
    if _EOM.search(raw):
        return Terms(TermsKind.EOM, days or 0, raw)
    if days is not None:
        return Terms(TermsKind.NET, days, raw)
    return Terms(TermsKind.UNKNOWN, None, raw)


def _end_of_month(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def derive_due_date(issue: date, terms: Terms) -> tuple[date | None, str | None]:
    """Return (due_date, human-readable calculation), or (None, None) if terms are unknown."""
    if terms.kind is TermsKind.DUE_ON_RECEIPT:
        return issue, f"{issue.isoformat()} (due on receipt)"
    if terms.kind is TermsKind.NET and terms.net_days is not None:
        due = issue + timedelta(days=terms.net_days)
        return due, f"{issue.isoformat()} + {terms.net_days} days ({terms.raw.strip()}) = {due.isoformat()}"
    if terms.kind is TermsKind.EOM:
        eom = _end_of_month(issue)
        due = eom + timedelta(days=terms.net_days or 0)
        extra = f" + {terms.net_days} days" if terms.net_days else ""
        return due, f"end of month {eom.isoformat()}{extra} ({terms.raw.strip()}) = {due.isoformat()}"
    return None, None
