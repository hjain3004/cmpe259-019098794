from datetime import date
from decimal import Decimal

import pytest

from cashbooks.contracts.records import TermsKind
from cashbooks.normalize.dates import DateParseError, parse_date
from cashbooks.normalize.fingerprint import fingerprint
from cashbooks.normalize.money import MoneyParseError, parse_amount, parse_money
from cashbooks.normalize.terms import derive_due_date, parse_terms
from cashbooks.normalize.vendors import normalize_name, resolve_vendor

# ---------------------------------------------------------------- money


@pytest.mark.parametrize("text,expected", [
    ("$1,118.25", "1118.25"),
    ("USD 842", "842.00"),
    ("Total: $842.00", "842.00"),
    ("(45.00)", "-45.00"),
    ("-$45.00", "-45.00"),
    ("($45.00)", "-45.00"),
    ("€85.5", "85.50"),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == Decimal(expected)


def test_parse_money_currency():
    assert parse_money("$842.00").currency == "USD"
    assert parse_money("EUR 1,200.00").currency == "EUR"
    assert parse_money("842.00", default_currency="USD").amount == Decimal("842.00")
    with pytest.raises(MoneyParseError):
        parse_money("842.00")
    with pytest.raises(MoneyParseError):
        parse_amount("n/a")


# ---------------------------------------------------------------- dates


@pytest.mark.parametrize("text", [
    "2026-08-13", "08/13/2026", "Aug 13, 2026", "August 13, 2026",
    "13 Aug 2026", "Aug 13th, 2026", "Aug  13, 2026",
])
def test_parse_date_formats(text):
    assert parse_date(text) == date(2026, 8, 13)


def test_parse_date_sept_and_errors():
    assert parse_date("Sept 2, 2026") == date(2026, 9, 2)
    with pytest.raises(DateParseError):
        parse_date("next Tuesday")


# ---------------------------------------------------------------- terms


@pytest.mark.parametrize("raw,kind,days", [
    ("Net 30", TermsKind.NET, 30),
    ("NET30", TermsKind.NET, 30),
    ("Terms: Net 15 days", TermsKind.NET, 15),
    ("Payment due within 15 days", TermsKind.NET, 15),
    ("Due on receipt", TermsKind.DUE_ON_RECEIPT, 0),
    ("Due upon receipt", TermsKind.DUE_ON_RECEIPT, 0),
    ("EOM", TermsKind.EOM, 0),
    ("Net 30 EOM", TermsKind.EOM, 30),
    ("Pay when you can", TermsKind.UNKNOWN, None),
    (None, TermsKind.UNKNOWN, None),
])
def test_parse_terms(raw, kind, days):
    t = parse_terms(raw)
    assert (t.kind, t.net_days) == (kind, days)


def test_derive_due_dates():
    issue = date(2026, 8, 13)
    assert derive_due_date(issue, parse_terms("Net 30"))[0] == date(2026, 9, 12)
    assert derive_due_date(date(2026, 8, 26), parse_terms("Net 15"))[0] == date(2026, 9, 10)
    assert derive_due_date(issue, parse_terms("Due on receipt"))[0] == issue
    assert derive_due_date(issue, parse_terms("EOM"))[0] == date(2026, 8, 31)
    assert derive_due_date(issue, parse_terms("Net 30 EOM"))[0] == date(2026, 9, 30)
    assert derive_due_date(date(2026, 2, 10), parse_terms("EOM"))[0] == date(2026, 2, 28)
    due, calc = derive_due_date(issue, parse_terms("Net 30"))
    assert "2026-08-13" in calc and "2026-09-12" in calc
    assert derive_due_date(issue, parse_terms("whenever")) == (None, None)


# ---------------------------------------------------------------- vendors

VENDORS = [
    {"vendor_id": "v_northside", "canonical_name": "Northside Supplies",
     "aliases": [{"alias": "Northside Supply Co.", "verified": True}]},
    {"vendor_id": "v_greenway", "canonical_name": "Greenway Produce", "aliases": []},
    {"vendor_id": "v_beanworks", "canonical_name": "BeanWorks Coffee Roasters",
     "aliases": [{"alias": "BeanWorks", "verified": True}]},
]


def test_normalize_name():
    assert normalize_name("Northside Supply Co.") == "northside supply"
    assert normalize_name("Greenway Produce, LLC") == "greenway produce"


def test_resolve_verified_alias_and_canonical():
    [c] = resolve_vendor("Northside Supply Co.", VENDORS)
    assert c.vendor_id == "v_northside" and c.via_verified_alias
    [c] = resolve_vendor("BEANWORKS", VENDORS)
    assert c.vendor_id == "v_beanworks"
    [c] = resolve_vendor("Greenway Produce LLC", VENDORS)
    assert c.vendor_id == "v_greenway" and c.score == 1.0


def test_resolve_fuzzy_and_unknown():
    cands = resolve_vendor("Northside Supplys", VENDORS)
    assert cands and cands[0].vendor_id == "v_northside" and not cands[0].via_verified_alias
    assert resolve_vendor("Bakery Depot", VENDORS) == []


# ---------------------------------------------------------------- fingerprints


def test_fingerprint_is_stable_and_masks():
    h1, last4 = fingerprint("004417829931")
    h2, _ = fingerprint("0044 1782 9931")
    assert h1 == h2 and last4 == "9931"
    assert fingerprint("008812345507")[0] != h1
    assert "004417829931" not in h1
    with pytest.raises(ValueError):
        fingerprint("12")


def test_short_vendor_names_and_ambiguity():
    [c] = resolve_vendor("greenway", VENDORS)
    assert c.vendor_id == "v_greenway"
    [c] = resolve_vendor("Northside", VENDORS)
    assert c.vendor_id == "v_northside"
    two = VENDORS + [{"vendor_id": "v_ns2", "canonical_name": "Northside Bakery", "aliases": []}]
    assert {c.vendor_id for c in resolve_vendor("Northside", two)} == {"v_northside", "v_ns2"}


def test_mask_digits_preserves_length():
    from cashbooks.normalize.fingerprint import mask_digits
    s = "Account: 004417829931, call (415) 555-0142 by 2026-09-12"
    out = mask_digits(s)
    assert len(out) == len(s) and "********9931" in out and "555-0142" in out and "2026-09-12" in out
