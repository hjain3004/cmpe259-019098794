"""Deterministic scoring of responses against gold, run logs, and the course CSV.

No LLM judge: money is checked to the cent with its currency, dates in any common
written form, answer type against the expected label, and citations at document
level so C1's page chunks and C3's field spans are compared fairly.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.contracts.response import AssistantResponse

SCORER_VERSION = "scorer_v3_1"

_MONEY = re.compile(r"^(-?\d+(?:\.\d{1,2})?)\s+([A-Z]{3})$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INV_ID = re.compile(r"\b[A-Za-z]{1,6}-\d+\b")

_ISO_CURRENCIES = frozenset({
    "USD", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF", "JPY", "CNY",
    "HKD", "SGD", "MXN", "INR", "SEK", "NOK", "DKK", "PLN", "BRL", "ZAR", "KRW",
})
_NON_USD_DOLLAR_CURRENCIES = frozenset({"CAD", "AUD", "NZD", "HKD", "SGD", "MXN"})
_NON_USD_DOLLAR_RE = re.compile(
    r"(?<![A-Za-z])(?:CAD|AUD|NZD|HKD|SGD|MXN)(?![A-Za-z])"
    r"|(?<![A-Za-z])(?:CA\$|AU\$|NZ\$|HK\$|SG\$|MX\$|C\$|A\$|S\$)"
)
_QUALIFIED_DOLLAR_PREFIXES: dict[str, str] = {
    "US$": "USD",
    "CA$": "CAD",
    "C$": "CAD",
    "AU$": "AUD",
    "A$": "AUD",
    "NZ$": "NZD",
    "HK$": "HKD",
    "SG$": "SGD",
    "S$": "SGD",
    "MX$": "MXN",
}
_UNAMBIGUOUS_SYMBOL_CURRENCY: dict[str, str] = {
    "€": "EUR",
    "£": "GBP",
}
_SCOPED_CURR_RE = re.compile(
    r"(?<![A-Za-z])(?:"
    r"(?i:all\s+(?:amounts?|figures?|totals?|balances?|values?|bills?|invoices?|payments?|prices?)\s+(?:are\s+)?(?:in\s+)?)(?P<c1>[A-Z]{3})"
    r"|(?i:all\s+(?:are\s+)?(?:in\s+)?)(?P<c2>[A-Z]{3})"
    r"|(?i:(?:currency|amounts?)\s*:\s*)(?P<c3>[A-Z]{3})"
    r"|(?i:amounts?\s+(?:are\s+)?in\s+)(?P<c4>[A-Z]{3})"
    r")(?![A-Za-z])"
)
_SCOPED_COMPOUND_AFTER_RE = re.compile(
    r"^\s*(?:,|/|&|\b(?:or|and)\b)\s*(?:[A-Z]{3}|[$€£¥])",
    re.I,
)
_NUM_MAG_RE = re.compile(
    r"(?<![\d.,])(?P<num>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?![\d])(?!\.\d)(?!,\d)"
)
_PREFIX_SYM_RE = re.compile(
    r"(?:(?<![A-Za-z])(?P<iso>[A-Z]{3})\s+)?"
    r"(?:(?<![A-Za-z0-9])(?P<sign1>[-−]))?"
    r"(?P<qsym>(?<![A-Za-z])(?:US\$|CA\$|AU\$|NZ\$|HK\$|SG\$|MX\$|C\$|A\$|S\$)|[$€£¥])"
    r"(?:\s*(?P<sign2>[-−])|\s*)$"
)
_PREFIX_PLAIN_RE = re.compile(
    r"(?:(?<![A-Za-z])(?P<iso>[A-Z]{3})\s+)?"
    r"(?:(?<![A-Za-z0-9])(?P<sign>[-−]))?$"
)
_SUFFIX_ISO_RE = re.compile(r"^\s*([A-Z]{3})(?![A-Za-z])")


def _is_identifier(phrase: str) -> bool:
    """Identifiers (invoice numbers, emails, account digits) stay strictly matched."""
    return bool("@" in phrase or _INV_ID.search(phrase) or re.search(r"\d{4,}", phrase))


def _check_must_not(text_lower: str, must_not: list[str]) -> tuple[list[str], list[str]]:
    """Return (hits, skipped) for must_not phrases, ignoring negated/quoted wording phrases."""
    from cashbooks.safety import _is_negated_or_quoted

    hits: list[str] = []
    skipped: list[str] = []
    for p in must_not:
        low = p.lower()
        if not low:
            continue
        if _is_identifier(p):
            if low in text_lower:
                hits.append(p)
            continue
        found = False
        unnegated = False
        pos = 0
        while True:
            idx = text_lower.find(low, pos)
            if idx == -1:
                break
            found = True
            if not _is_negated_or_quoted(text_lower, idx, idx + len(low)):
                unnegated = True
                break
            pos = idx + len(low)
        if unnegated:
            hits.append(p)
        elif found:
            skipped.append(p)
    return hits, skipped


def money_variants(amount: Decimal) -> set[str]:
    a = abs(amount)
    plain, comma = f"{a:.2f}", f"{a:,.2f}"
    out = {plain, comma, f"${plain}", f"${comma}"}
    if a == a.to_integral_value():
        whole, whole_c = f"{int(a)}", f"{int(a):,}"
        out |= {f"${whole}", f"${whole_c}"}
    return out


def date_variants(d: date) -> set[str]:
    return {
        d.isoformat(), d.strftime("%m/%d/%Y"), f"{d.month}/{d.day}/{d.year}", f"{d.month}/{d.day}",
        d.strftime("%b %d, %Y"), d.strftime("%B %d, %Y"), f"{d.strftime('%b')} {d.day}, {d.year}",
        f"{d.strftime('%B')} {d.day}, {d.year}", f"{d.strftime('%b')} {d.day}", f"{d.strftime('%B')} {d.day}",
        f"{d.day} {d.strftime('%b')} {d.year}", f"{d.day} {d.strftime('%B')} {d.year}",
    }


def _text(resp: AssistantResponse) -> str:
    parts = [resp.answer, resp.clarifying_question or "", resp.next_step or ""]
    parts += resp.risk_indicators
    if resp.calculation:
        parts += resp.calculation.steps
    return " ".join(parts)


_UNPAID_RE = re.compile(
    r"\b(?:unpaid|not\s+paid|not\s+been\s+paid|has\s+not\s+been\s+paid|hasn't\s+been\s+paid|open|outstanding)\b",
    re.I,
)
_PARTIAL_RE = re.compile(
    r"\b(?:partially\s+paid|partly\s+paid|partial(?:\s+payment)?)\b",
    re.I,
)
_PAID_NEG_PREFIX = re.compile(
    r"(?:\b(?:not|never|un|partially|partly|haven't|hasn't|wasn't|isn't)\s+(?:been\s+|yet\s+|already\s+)?)$",
    re.I,
)
_PAID_WORD_RE = re.compile(r"\b(?:paid\s+in\s+full|paid|settled)\b", re.I)


_OVERPAID_RE = re.compile(
    r"\b(?:overpaid|over-paid|paid\s+twice|paid\s+two\s+times|paid\s+(?:it\s+)?more\s+than\s+once|double[-\s]paid"
    r"|duplicate\s+payments?|double\s+payments?|paid\s+(?:it\s+)?again)\b",
    re.I,
)


def _match_overpaid(text: str) -> bool:
    return _OVERPAID_RE.search(text) is not None


def _match_paid(text: str) -> bool:
    for m in _PAID_WORD_RE.finditer(text):
        prefix = text[max(0, m.start() - 35) : m.start()]
        if not _PAID_NEG_PREFIX.search(prefix):
            return True
    return False


def _find_scoped_currency(text: str, valid_iso: frozenset[str]) -> tuple[str, int] | None:
    """Return (currency, scope_start_index) when text has a single unambiguous, uncontradicted
    scoped currency declaration (e.g. 'All amounts in USD' or '(all USD)').

    Returns None if no declaration exists, if a declaration is compound/ambiguous ('USD or EUR'),
    if multiple conflicting declarations appear, or if a conflicting currency appears in scope.
    """
    decls: list[tuple[int, str]] = []
    for m in _SCOPED_CURR_RE.finditer(text):
        code = m.group("c1") or m.group("c2") or m.group("c3") or m.group("c4")
        if not code or code not in valid_iso:
            continue
        if _SCOPED_COMPOUND_AFTER_RE.match(text[m.end() :]):
            return None
        decls.append((m.end(), code))
    if not decls:
        return None
    currencies = {c for _, c in decls}
    if len(currencies) > 1:
        return None
    scoped_curr = decls[0][1]
    scope_start = decls[0][0]
    tail = text[scope_start:]

    # Reject scope if any conflicting ISO currency or incompatible currency symbol appears in scope.
    for other in valid_iso - {scoped_curr}:
        if re.search(rf"(?<![A-Za-z]){re.escape(other)}(?![A-Za-z])", tail):
            return None
    for qpref, qcurr in _QUALIFIED_DOLLAR_PREFIXES.items():
        if qcurr != scoped_curr and re.search(rf"(?<![A-Za-z]){re.escape(qpref)}", tail):
            return None
    for sym, scurr in _UNAMBIGUOUS_SYMBOL_CURRENCY.items():
        if scurr != scoped_curr and sym in tail:
            return None
    if scoped_curr not in ({"USD"} | _NON_USD_DOLLAR_CURRENCIES) and "$" in tail:
        return None
    return scoped_curr, scope_start


def _unpack_expected(expected: str | dict, amount_semantics: str | None = None) -> tuple[str, str]:
    """Extract (expected_value_str, semantics) from a string or typed spec dict.

    Supported explicit semantics:
      - 'signed_money' (default for '<amount> <CUR>')
      - 'txn_magnitude' (bank outflow: accepts positive magnitude or negative statement debit)
      - 'non_money_number' (default for bare numeric strings)
    """
    if isinstance(expected, dict):
        kind = str(expected.get("kind") or expected.get("type") or "").strip().lower()
        val = str(expected.get("value", "")).strip()
        if not val and "amount" in expected:
            cur = str(expected.get("currency", "")).strip()
            val = f"{expected['amount']} {cur}".strip()
        sem = amount_semantics or kind or "default"
        return val, sem
    return str(expected).strip(), (amount_semantics or "default")


def _match_money_in_text(
    text: str,
    expected_amount: Decimal,
    expected_currency: str,
    calc_currency_conflicts: bool = False,
    allow_negative_magnitude: bool = False,
) -> bool:
    """Match a bounded money mention with exact Decimal value, sign/magnitude, and established currency."""
    valid_iso = _ISO_CURRENCIES | {expected_currency}
    has_non_usd_dollar = _NON_USD_DOLLAR_RE.search(text) is not None
    scoped = _find_scoped_currency(text, valid_iso)

    for m in _NUM_MAG_RE.finditer(text):
        before = text[: m.start()]
        after = text[m.end() :]

        # Skip numbers that are part of alphanumeric identifiers like INV-42 or GP-221.
        if re.search(r"[A-Za-z0-9][-−]$", before):
            continue

        prefix_iso: str | None = None
        qsym: str | None = None
        sign1: str | None = None
        sign2: str | None = None

        pm_sym = _PREFIX_SYM_RE.search(before)
        if pm_sym:
            prefix_iso = pm_sym.group("iso")
            sign1 = pm_sym.group("sign1")
            qsym = pm_sym.group("qsym")
            sign2 = pm_sym.group("sign2")
            if sign1 and sign2:
                continue
        else:
            pm_plain = _PREFIX_PLAIN_RE.search(before)
            if pm_plain:
                prefix_iso = pm_plain.group("iso")
                sign1 = pm_plain.group("sign")

        if prefix_iso not in valid_iso:
            prefix_iso = None

        sm = _SUFFIX_ISO_RE.match(after)
        suffix_iso = sm.group(1) if (sm and sm.group(1) in valid_iso) else None

        try:
            val = Decimal(m.group("num").replace(",", ""))
        except InvalidOperation:
            continue
        if sign1 or sign2:
            val = -val

        if allow_negative_magnitude:
            if abs(val) != abs(expected_amount):
                continue
        else:
            if val != expected_amount:
                continue

        q_curr = _QUALIFIED_DOLLAR_PREFIXES.get(qsym or "")
        explicit_codes = {c for c in (prefix_iso, q_curr, suffix_iso) if c}
        if len(explicit_codes) > 1:
            continue
        if len(explicit_codes) == 1:
            mention_curr = next(iter(explicit_codes))
            if qsym in _UNAMBIGUOUS_SYMBOL_CURRENCY and _UNAMBIGUOUS_SYMBOL_CURRENCY[qsym] != mention_curr:
                continue
            if mention_curr == expected_currency:
                return True
            continue

        if qsym in _UNAMBIGUOUS_SYMBOL_CURRENCY:
            if _UNAMBIGUOUS_SYMBOL_CURRENCY[qsym] == expected_currency:
                return True
            continue

        if qsym == "$":
            if scoped is not None and m.start() >= scoped[1]:
                if scoped[0] == expected_currency and not calc_currency_conflicts:
                    return True
                continue
            if expected_currency == "USD" and not has_non_usd_dollar and not calc_currency_conflicts:
                return True
            continue

        if qsym is None and scoped is not None and m.start() >= scoped[1]:
            if scoped[0] == expected_currency and not calc_currency_conflicts:
                return True
            continue

    return False


def _match_bare_number(exp: str, text: str, allow_negative_magnitude: bool = False) -> bool:
    """Match a standalone bare number (with optional valid thousands commas) without substring collisions."""
    is_neg = exp.startswith("-")
    raw_mag = exp[1:] if is_neg else exp
    parts = raw_mag.split(".")
    int_part = parts[0]
    frac_part = f".{parts[1]}" if len(parts) == 2 else ""
    candidates = [raw_mag]
    if len(int_part) >= 4:
        grouped = f"{int(int_part):,}{frac_part}"
        if grouped != raw_mag:
            candidates.append(grouped)
    alt = "|".join(re.escape(c) for c in candidates)
    neg_pat = rf"(?<![A-Za-z0-9])[-−](?:[$€£¥]\s*)?(?:{alt})(?![\d])(?!\.\d)(?!,\d)"
    if is_neg:
        return re.search(neg_pat, text) is not None
    if allow_negative_magnitude and re.search(neg_pat, text) is not None:
        return True
    for m in re.finditer(rf"(?<![A-Za-z\d.,\-−])(?:{alt})(?![\d])(?!\.\d)(?!,\d)", text):
        before = text[: m.start()]
        if re.search(r"(?<![A-Za-z0-9])[-−][$€£¥]\s*$", before):
            continue
        return True
    return False


def check_value(expected: str | dict, resp: AssistantResponse, *, amount_semantics: str | None = None) -> bool:
    exp_str, sem = _unpack_expected(expected, amount_semantics=amount_semantics)
    allow_mag = sem == "txn_magnitude"
    text = _text(resp)
    m = _MONEY.match(exp_str)
    if m:
        try:
            amount = Decimal(m.group(1))
        except InvalidOperation:
            return False
        currency = m.group(2)
        calc = resp.calculation.result if resp.calculation else None
        if calc and calc.currency == currency:
            if (allow_mag and abs(calc.amount) == abs(amount)) or (not allow_mag and calc.amount == amount):
                return True
        calc_conflicts = bool(
            calc
            and calc.currency != currency
            and ((allow_mag and abs(calc.amount) == abs(amount)) or (not allow_mag and calc.amount == amount))
        )
        return _match_money_in_text(
            text,
            amount,
            currency,
            calc_currency_conflicts=calc_conflicts,
            allow_negative_magnitude=allow_mag,
        )
    if _DATE.match(exp_str):
        d = date.fromisoformat(exp_str)
        return any(v.lower() in text.lower() for v in date_variants(d))
    exp = exp_str.lower()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", exp):  # a bare number must stand alone, not inside a longer number
        return _match_bare_number(exp, text, allow_negative_magnitude=allow_mag)
    if exp in ("yes", "no"):
        return re.search(rf"\b{exp}\b", text.lower()) is not None
    if exp in ("unpaid", "open"):
        return _UNPAID_RE.search(text) is not None
    if exp in ("partially paid", "partly paid", "partial"):
        return _PARTIAL_RE.search(text) is not None
    if exp == "paid":
        return _match_paid(text)
    if exp == "overpaid":
        return _match_overpaid(text)
    return exp in text.lower()


def check_sign_only_mismatch(expected: str | dict, resp: AssistantResponse) -> bool:
    """True when a positive unannotated expected amount fails strict default matching solely
    because the reply expressed it as a negative statement outflow with exact magnitude and currency."""
    exp_str, sem = _unpack_expected(expected)
    if sem == "txn_magnitude":
        return False
    m = _MONEY.match(exp_str)
    if m:
        if Decimal(m.group(1)) <= 0:
            return False
        if check_value(expected, resp):
            return False
        return check_value(exp_str, resp, amount_semantics="txn_magnitude")
    if re.fullmatch(r"\d+(?:\.\d+)?", exp_str) and Decimal(exp_str) > 0:
        if check_value(expected, resp):
            return False
        return check_value(exp_str, resp, amount_semantics="txn_magnitude")
    return False


def doc_level(evidence_id: str) -> str:
    """span_inv_NS-1048_total -> inv_NS-1048; span_msg_m03 -> msg_m03; txn_0193 -> txn_0193."""
    parts = evidence_id.split("_")
    if parts[0] == "span" and len(parts) >= 3:
        return f"{parts[1]}_{parts[2]}"
    return evidence_id


@dataclass
class TurnScore:
    parsed: bool
    answerability_ok: bool
    values: dict[str, bool] = field(default_factory=dict)
    evidence_recall: float | None = None
    evidence_precision: float | None = None
    must_not_hits: list[str] = field(default_factory=list)
    must_not_skipped: list[str] = field(default_factory=list)
    success: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def score_turn(resp: AssistantResponse | None, expected: Answerability, gold_values: dict, gold_evidence: list[str],
               must_not: list[str]) -> TurnScore:
    if resp is None:
        return TurnScore(parsed=False, answerability_ok=False, success=False)
    ans_ok = resp.answerability == expected
    values = {k: check_value(v if isinstance(v, dict) else str(v), resp) for k, v in (gold_values or {}).items()}
    cited = {doc_level(c.evidence_id) for c in resp.evidence}
    gold = set(gold_evidence or [])
    recall = len(cited & gold) / len(gold) if gold else None
    precision = (len(cited & gold) / len(cited) if cited else 0.0) if gold else None
    text = _text(resp).lower()
    hits, skipped = _check_must_not(text, must_not)
    success = ans_ok and all(values.values()) and not hits and (recall is None or recall > 0)
    return TurnScore(True, ans_ok, values, recall, precision, hits, skipped, success)


# ---------------------------------------------------------------- logs


def write_log(rows: Iterable[LogRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(r.model_dump_json() + "\n")


def read_log(path: Path) -> list[LogRow]:
    with open(path, encoding="utf-8") as f:
        return [LogRow.model_validate_json(line) for line in f if line.strip()]


def export_course_csv(rows: list[LogRow], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["configuration", "query_id", "turn", "query", "expected_behavior",
                                          "response", "success", "notes"])
        w.writeheader()
        for r in rows:
            proj = r.course_projection()
            w.writerow({"configuration": r.configuration, "query_id": r.query_id, "turn": r.turn_index, **proj})


_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


def _extract_reply_stats(raw_response: str) -> tuple[int, int, str | None] | None:
    """Return (citation_count, answer_word_count, answerability) from a raw JSON reply, or None."""
    if not raw_response:
        return None
    raw = raw_response.strip()
    m = _FENCE.fullmatch(raw)
    if m:
        raw = m.group(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    cites = data.get("evidence")
    cite_count = len(cites) if isinstance(cites, list) else 0
    answer = data.get("answer")
    word_count = len(str(answer).split()) if isinstance(answer, str) else 0
    ans_type = data.get("answerability") if isinstance(data.get("answerability"), str) else None
    return cite_count, word_count, ans_type


def summarize(rows: list[LogRow]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        s = out.setdefault(r.configuration, {
            "turns": 0, "parsed": 0, "successes": 0, "answer_type_ok": 0,
            "values_ok": 0, "values_total": 0, "latency_ms": [], "tokens": [],
            "recalls": [], "precisions": [], "citations": [], "words": [],
            "unwarranted_warnings": 0, "unwarranted_warning_eligible": 0,
            "over_abstentions": 0, "over_abstention_eligible": 0,
        })
        s["turns"] += 1
        s["parsed"] += int(r.parsed_ok)
        s["successes"] += int(bool(r.success))
        s["answer_type_ok"] += int(bool(r.scores.get("answerability_ok")))
        vals = r.scores.get("values") or {}
        s["values_ok"] += sum(1 for v in vals.values() if v)
        s["values_total"] += len(vals)
        if r.scores.get("evidence_recall") is not None:
            s["recalls"].append(float(r.scores["evidence_recall"]))
        if r.scores.get("evidence_precision") is not None:
            s["precisions"].append(float(r.scores["evidence_precision"]))
        ans_type = None
        if r.parsed_ok:
            stats = _extract_reply_stats(r.raw_response)
            if stats is not None:
                s["citations"].append(stats[0])
                s["words"].append(stats[1])
                ans_type = stats[2]
        if r.expected in (Answerability.ANSWER, Answerability.CLARIFY):
            s["unwarranted_warning_eligible"] += 1
            if ans_type == Answerability.WARN.value:
                s["unwarranted_warnings"] += 1
        if r.expected == Answerability.ANSWER:
            s["over_abstention_eligible"] += 1
            if ans_type == Answerability.ABSTAIN.value:
                s["over_abstentions"] += 1
        s["latency_ms"].append(r.latency_ms)
        s["tokens"].append(r.input_tokens + r.output_tokens)
    for s in out.values():
        n = s["turns"] or 1
        lat = sorted(s.pop("latency_ms"))
        tok = s.pop("tokens")
        rec = s.pop("recalls")
        prec = s.pop("precisions")
        cites = s.pop("citations")
        words = sorted(s.pop("words"))
        s["success_rate"] = round(s["successes"] / n, 3)
        s["answer_type_accuracy"] = round(s["answer_type_ok"] / n, 3)
        s["value_accuracy"] = round(s["values_ok"] / s["values_total"], 3) if s["values_total"] else None
        s["unwarranted_warning_rate"] = (
            round(s["unwarranted_warnings"] / s["unwarranted_warning_eligible"], 3)
            if s["unwarranted_warning_eligible"] else None
        )
        s["over_abstention_rate"] = (
            round(s["over_abstentions"] / s["over_abstention_eligible"], 3)
            if s["over_abstention_eligible"] else None
        )
        s["mean_evidence_recall"] = round(sum(rec) / len(rec), 3) if rec else None
        s["mean_evidence_precision"] = round(sum(prec) / len(prec), 3) if prec else None
        s["mean_citations"] = round(sum(cites) / len(cites), 2) if cites else None
        s["median_words"] = words[len(words) // 2] if words else None
        s["p90_words"] = words[max(0, math.ceil(0.9 * len(words)) - 1)] if words else None
        s["under_120_words_share"] = round(sum(1 for w in words if w < 120) / len(words), 3) if words else None
        s["median_latency_s"] = round(lat[len(lat) // 2] / 1000, 2) if lat else None
        s["mean_tokens"] = round(sum(tok) / len(tok)) if tok else None
    return out


def conversation_success(rows: list[LogRow]) -> dict[str, dict[str, bool]]:
    """A conversation succeeds only when every scored turn succeeds."""
    out: dict[str, dict[str, bool]] = {}
    for r in rows:
        c = out.setdefault(r.configuration, {})
        c[r.query_id] = c.get(r.query_id, True) and bool(r.success)
    return out


def dump_json(obj, path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


_LABELS = ["lookup", "aggregation", "temporal", "linking", "comparison", "dialogue", "abstention"]


def _load_query_labels() -> dict[str, list[str]]:
    qpath = Path(__file__).resolve().parents[3] / "evaluation" / "queries.yaml"
    if not qpath.exists():
        return {}
    import yaml

    data = yaml.safe_load(qpath.read_text(encoding="utf-8")) or {}
    return {c["id"]: list(c.get("labels", [])) for c in data.get("conversations", []) if "id" in c}


def summarize_by_label(rows: list[LogRow], query_labels: dict[str, list[str]]) -> dict[str, dict[str, dict[str, int]]]:
    """Per-label, per-config turn counts: {label: {config: {'correct': int, 'total': int}}}."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    configs = list(dict.fromkeys(r.configuration for r in rows))
    for lbl in _LABELS:
        out[lbl] = {c: {"correct": 0, "total": 0} for c in configs}
    for r in rows:
        for lbl in query_labels.get(r.query_id, []):
            if lbl not in out:
                out[lbl] = {c: {"correct": 0, "total": 0} for c in configs}
            cell = out[lbl][r.configuration]
            cell["total"] += 1
            cell["correct"] += int(bool(r.success))
    return out


def write_run_outputs(rows: list[LogRow], out: Path, run_id: str, model: str, commit: str, bundle: str,
                      conv_ids: list[str], scored_turns: int, prompt_version: str,
                      query_labels: dict[str, list[str]] | None = None) -> list[str]:
    """course.csv, summary.json and summary.md for one run; returns the summary.md lines."""
    export_course_csv(rows, out / "course.csv")
    summary = summarize(rows)
    conv = conversation_success(rows)
    for cname, per in conv.items():
        summary[cname]["conversations"] = len(per)
        summary[cname]["conversation_successes"] = sum(per.values())
    qlabels = query_labels if query_labels is not None else _load_query_labels()
    by_label = summarize_by_label(rows, qlabels) if qlabels else {}
    dump_json({"run": run_id, "model": model, "commit": commit, "bundle": bundle,
               "configs": summary, "by_label": by_label, "per_conversation": conv}, out / "summary.json")
    lines = [f"# Run {run_id}", "", f"Model `{model}`, prompt `{prompt_version}`, commit `{commit}`, "
             f"scenario `{Path(bundle).name}`, {len(conv_ids)} conversations, {scored_turns} scored turns.", "",
             "| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for cname, s in summary.items():
        va = s["value_accuracy"]
        lines.append(f"| {cname} | {s['successes']}/{s['turns']} ({s['success_rate']:.0%}) | "
                     f"{s['conversation_successes']}/{s['conversations']} | {s['answer_type_accuracy']:.0%} | "
                     f"{'n/a' if va is None else format(va, '.0%')} | {s['parsed']}/{s['turns']} | "
                     f"{s['median_latency_s']} | {s['mean_tokens']} |")
    lines += [
        "",
        "## Error rates",
        "",
        "| Config | Unwarranted-warning rate | Over-abstention rate |",
        "| --- | --- | --- |",
    ]
    for cname, s in summary.items():
        uwr = s["unwarranted_warning_rate"]
        oar = s["over_abstention_rate"]
        uw_str = "n/a" if uwr is None else f"{s['unwarranted_warnings']}/{s['unwarranted_warning_eligible']} ({uwr:.0%})"
        oa_str = "n/a" if oar is None else f"{s['over_abstentions']}/{s['over_abstention_eligible']} ({oar:.0%})"
        lines.append(f"| {cname} | {uw_str} | {oa_str} |")
    lines += [
        "",
        "## Grounding and usability",
        "",
        "| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cname, s in summary.items():
        mr = s["mean_evidence_recall"]
        mp = s["mean_evidence_precision"]
        mc = s["mean_citations"]
        mw = s["median_words"]
        pw = s["p90_words"]
        u120 = s["under_120_words_share"]
        lines.append(
            f"| {cname} | {'n/a' if mr is None else f'{mr:.3f}'} | {'n/a' if mp is None else f'{mp:.3f}'} | "
            f"{'n/a' if mc is None else f'{mc:.2f}'} | {'n/a' if mw is None else mw} | "
            f"{'n/a' if pw is None else pw} | {'n/a' if u120 is None else f'{u120:.0%}'} |"
        )
    if by_label:
        cfg_names = list(summary.keys())
        lines += [
            "",
            "## Per-question-type turn success",
            "",
            "| Label | " + " | ".join(cfg_names) + " |",
            "| --- |" + " --- |" * len(cfg_names),
        ]
        for lbl, per_cfg in by_label.items():
            cells = [f"{per_cfg[c]['correct']}/{per_cfg[c]['total']}" if c in per_cfg else "0/0" for c in cfg_names]
            lines.append(f"| {lbl} | " + " | ".join(cells) + " |")
    lines += ["", "## Conversation success", "", "| Conversation | " + " | ".join(conv) + " |",
              "| --- |" + " --- |" * len(conv)]
    for q in conv_ids:
        lines.append(f"| {q} | " + " | ".join("pass" if conv[c].get(q) else "fail" for c in conv) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    return lines
