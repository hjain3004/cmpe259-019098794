"""Vendor-name normalization and alias resolution.

Resolution selects among the owner's known vendors (approved aliases first,
then a similarity threshold) rather than judging pairs in isolation. It returns
every candidate above the threshold so callers can report ambiguity.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "co", "company", "corp",
    "corporation", "plc", "lp", "llp", "the",
}

DEFAULT_THRESHOLD = 0.85  # set on development bundles only


def normalize_name(name: str) -> str:
    """'Northside Supply Co.' -> 'northside supply'."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    tokens = re.findall(r"[a-z0-9]+", s)
    tokens = [t for t in tokens if t not in _SUFFIXES]
    return " ".join(tokens)


def _stem(token: str) -> str:
    return token[:-1] if len(token) > 4 and token.endswith("s") else token


def similarity(a: str, b: str) -> float:
    na = " ".join(_stem(t) for t in normalize_name(a).split())
    nb = " ".join(_stem(t) for t in normalize_name(b).split())
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


@dataclass(frozen=True)
class VendorCandidate:
    vendor_id: str
    matched_on: str  # the name or alias that matched
    score: float
    via_verified_alias: bool


def resolve_vendor(
    name: str,
    vendors: list[dict],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[VendorCandidate]:
    """vendors: [{"vendor_id", "canonical_name", "aliases": [{"alias", "verified"}]}].

    An exact normalized match on the canonical name or a verified alias wins
    outright. Otherwise all names scoring at or above the threshold are returned,
    best first, one entry per vendor.
    """
    target = normalize_name(name)
    target_tokens = target.split()
    exact: list[VendorCandidate] = []
    fuzzy: dict[str, VendorCandidate] = {}
    for v in vendors:
        names = [(v["canonical_name"], True)] + [(a["alias"], a.get("verified", False)) for a in v.get("aliases", [])]
        for n, verified in names:
            if verified and normalize_name(n) == target:
                exact.append(VendorCandidate(v["vendor_id"], n, 1.0, n != v["canonical_name"]))
                break
            score = similarity(name, n)
            # Owners shorten names ("Greenway", "the Northside one"): a query whose
            # words all start the vendor's name counts as a candidate.
            name_tokens = normalize_name(n).split()
            if target_tokens and name_tokens[: len(target_tokens)] == target_tokens:
                score = max(score, 0.9)
            if score >= threshold:
                best = fuzzy.get(v["vendor_id"])
                if best is None or score > best.score:
                    fuzzy[v["vendor_id"]] = VendorCandidate(v["vendor_id"], n, round(score, 3), False)
    if exact:
        return exact
    return sorted(fuzzy.values(), key=lambda c: (-c.score, c.vendor_id))
