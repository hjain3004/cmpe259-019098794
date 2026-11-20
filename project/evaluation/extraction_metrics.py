"""NER-style entity extraction precision, recall, and F1 for CashBooks Assist.

Evaluates extracted.sqlite against gold records (load_gold) across:
  - Development: cafe_01, plumbing_01
  - Held-out: landscaping_01 (read-only)
  - Real documents (SROIE): company, date, total from saved prediction JSONL (aggregates only)

NER-style matching: each normalized field or 4-tuple line item is one unit;
a partially correct value counts as both 1 false positive and 1 false negative.

    cd project
    python evaluation/extraction_metrics.py
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from cashbooks.normalize.money import MoneyParseError, parse_amount
from cashbooks.store.db import Store
from cashbooks.store.load_gold import load_gold

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_DEV = [PROJECT / "data" / "dev" / "cafe_01", PROJECT / "data" / "dev" / "plumbing_01"]
DEFAULT_HELDOUT = [PROJECT / "data" / "test" / "landscaping_01"]
DEFAULT_SROIE = PROJECT / "data" / "real" / "runs" / "20261117-163026-sroie-claude-haiku-5-5.jsonl"
DEFAULT_OUT = PROJECT / "evaluation" / "results" / "final"

HEADER_FIELDS = (
    "vendor",
    "invoice_number",
    "issue_date",
    "due_date",
    "payment_terms",
    "subtotal",
    "tax",
    "total",
    "currency",
    "remit_account_last4",
)
ALL_FIELDS = HEADER_FIELDS + ("line_items",)

_DMY_FORMATS = (
    "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y",
    "%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
    "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y", "%d/%b/%y", "%d %b %y", "%b %d, %Y",
    "%B %d, %Y", "%d%b%Y", "%Y%m%d", "%d%m%Y", "%m/%d/%Y", "%m/%d/%y",
)


def _norm_text(val: str | None) -> str | None:
    if not val:
        return None
    cleaned = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", val.upper())).strip()
    return cleaned or None


def _norm_terms(val: str | None) -> str | None:
    if not val:
        return None
    cleaned = re.sub(r"\s+", " ", val.strip()).lower()
    return cleaned or None


def _norm_dec(val: Decimal | str | int | float | None) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _norm_date(val: date | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val.isoformat()
    s = str(val).strip()
    return s or None


def _norm_sroie_date(text: str | None) -> str | None:
    if not text:
        return None
    t = re.sub(r"\s+", " ", text.strip().replace(",", " ")).strip()
    m = re.search(
        r"\d{1,4}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}[ /\-]?[A-Za-z]{3,9}[ /\-]?\d{2,4}"
        r"|[A-Za-z]{3,9} \d{1,2} \d{4}|\b\d{8}\b",
        t,
    )
    cand = m.group() if m else t
    for fmt in _DMY_FORMATS:
        try:
            parsed = datetime.strptime(cand.title() if "%b" in fmt or "%B" in fmt else cand, fmt).date()
            return parsed.isoformat()
        except ValueError:
            continue
    return re.sub(r"\s+", "", text.upper()) or None


def _norm_sroie_money(text: str | None) -> Decimal | None:
    if not text:
        return None
    try:
        return abs(parse_amount(text)).quantize(Decimal("0.01"))
    except (MoneyParseError, InvalidOperation):
        return None


def compare_entity_unit(gold_val: Any, pred_val: Any) -> tuple[int, int, int]:
    """NER-style exact unit match returning (tp, fp, fn)."""
    if gold_val is None and pred_val is None:
        return (0, 0, 0)
    if gold_val is not None and pred_val is None:
        return (0, 0, 1)
    if gold_val is None and pred_val is not None:
        return (0, 1, 0)
    if gold_val == pred_val:
        return (1, 0, 0)
    return (0, 1, 1)


def compare_line_items(
    gold_lines: list[tuple[Any, ...]],
    pred_lines: list[tuple[Any, ...]],
) -> tuple[int, int, int]:
    """NER-style multiset match on normalized line-item 4-tuples (desc, qty, unit_price, line_total)."""
    cg = Counter(gold_lines)
    cp = Counter(pred_lines)
    tp = sum(min(cg[k], cp[k]) for k in set(cg) & set(cp))
    fp = len(pred_lines) - tp
    fn = len(gold_lines) - tp
    return (tp, fp, fn)


def prf_from_counts(tp: int, fp: int, fn: int) -> dict[str, Any]:
    p = tp / (tp + fp) if (tp + fp) > 0 else None
    r = tp / (tp + fn) if (tp + fn) > 0 else None
    if p is not None and r is not None:
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
    else:
        f1 = None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def _extract_bill_fields(store: Store, bill: Any) -> dict[str, Any]:
    vendor_raw = bill.printed_vendor_name or (store.vendor_name(bill.vendor_id) if bill.vendor_id else None)
    return {
        "vendor": _norm_text(vendor_raw),
        "invoice_number": bill.invoice_number.strip().upper() if bill.invoice_number else None,
        "issue_date": _norm_date(bill.issue_date),
        "due_date": _norm_date(bill.stated_due_date or bill.due_date_derived),
        "payment_terms": _norm_terms(bill.payment_terms_raw),
        "subtotal": _norm_dec(bill.subtotal),
        "tax": _norm_dec(bill.tax),
        "total": _norm_dec(bill.total),
        "currency": bill.currency.strip().upper() if bill.currency else None,
        "remit_account_last4": bill.remit_account_last4.strip() if bill.remit_account_last4 else None,
    }


def _extract_line_tuples(store: Store, bill_id: str) -> list[tuple[Any, ...]]:
    return [
        (
            re.sub(r"\s+", " ", (ln.description or "").strip()).lower(),
            _norm_dec(ln.quantity),
            _norm_dec(ln.unit_price),
            _norm_dec(ln.line_total),
        )
        for ln in store.lines(bill_id)
    ]


def evaluate_bundle_stores(gold_store: Store, ext_store: Store) -> dict[str, Any]:
    """Compare all bills and line items between gold_store and ext_store after normalization."""
    gold_by_doc = {b.doc_id: b for b in gold_store.bills()}
    ext_by_doc = {b.doc_id: b for b in ext_store.bills()}
    all_docs = sorted(set(gold_by_doc) | set(ext_by_doc))

    counts: dict[str, list[int]] = {f: [0, 0, 0] for f in ALL_FIELDS}
    for doc_id in all_docs:
        gb = gold_by_doc.get(doc_id)
        eb = ext_by_doc.get(doc_id)
        gf = _extract_bill_fields(gold_store, gb) if gb else {f: None for f in HEADER_FIELDS}
        ef = _extract_bill_fields(ext_store, eb) if eb else {f: None for f in HEADER_FIELDS}
        for f in HEADER_FIELDS:
            tp, fp, fn = compare_entity_unit(gf[f], ef[f])
            counts[f][0] += tp
            counts[f][1] += fp
            counts[f][2] += fn

        gl = _extract_line_tuples(gold_store, gb.bill_id) if gb else []
        el = _extract_line_tuples(ext_store, eb.bill_id) if eb else []
        tp, fp, fn = compare_line_items(gl, el)
        counts["line_items"][0] += tp
        counts["line_items"][1] += fp
        counts["line_items"][2] += fn

    fields = {f: prf_from_counts(*counts[f]) for f in ALL_FIELDS}
    tot_tp = sum(counts[f][0] for f in ALL_FIELDS)
    tot_fp = sum(counts[f][1] for f in ALL_FIELDS)
    tot_fn = sum(counts[f][2] for f in ALL_FIELDS)
    return {
        "documents": len(gold_by_doc),
        "extracted_documents": len(ext_by_doc),
        "fields": fields,
        "overall_micro": prf_from_counts(tot_tp, tot_fp, tot_fn),
    }


def evaluate_bundle(bundle: Path) -> dict[str, Any]:
    ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
    biz_id = ledger["business"]["business_id"]
    gold_store, _ = load_gold(bundle)
    conn = sqlite3.connect(str(bundle / "extracted.sqlite"))
    conn.row_factory = sqlite3.Row
    try:
        ext_store = Store(conn, biz_id)
        res = evaluate_bundle_stores(gold_store, ext_store)
    finally:
        conn.close()
    res["bundle"] = bundle.name
    return res


def pool_bundle_results(bundle_results: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, list[int]] = {f: [0, 0, 0] for f in ALL_FIELDS}
    docs = 0
    for br in bundle_results:
        docs += br["documents"]
        for f in ALL_FIELDS:
            fs = br["fields"][f]
            counts[f][0] += fs["tp"]
            counts[f][1] += fs["fp"]
            counts[f][2] += fs["fn"]
    fields = {f: prf_from_counts(*counts[f]) for f in ALL_FIELDS}
    tot_tp = sum(counts[f][0] for f in ALL_FIELDS)
    tot_fp = sum(counts[f][1] for f in ALL_FIELDS)
    tot_fn = sum(counts[f][2] for f in ALL_FIELDS)
    return {
        "documents": docs,
        "fields": fields,
        "overall_micro": prf_from_counts(tot_tp, tot_fp, tot_fn),
    }


def evaluate_sroie_jsonl(jsonl_path: Path) -> dict[str, Any]:
    """Compute NER-style P/R/F1 for SROIE (company, date, total); returns aggregates only."""
    counts = {"company": [0, 0, 0], "date": [0, 0, 0], "total": [0, 0, 0]}
    n_docs = 0
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n_docs += 1
            row = json.loads(line)
            gold = row.get("gold") or {}
            pred = row.get("pred") or {}
            if pred.get("error"):
                pred_vendor = None
                pred_date = None
                pred_total = None
            else:
                pred_vendor = _norm_text(pred.get("vendor"))
                pred_date = _norm_sroie_date(pred.get("date"))
                pred_total = _norm_sroie_money(pred.get("total"))

            pairs = (
                ("company", _norm_text(gold.get("company")), pred_vendor),
                ("date", _norm_sroie_date(gold.get("date")), pred_date),
                ("total", _norm_sroie_money(gold.get("total")), pred_total),
            )
            for fname, gv, pv in pairs:
                tp, fp, fn = compare_entity_unit(gv, pv)
                counts[fname][0] += tp
                counts[fname][1] += fp
                counts[fname][2] += fn

    fields = {f: prf_from_counts(*counts[f]) for f in ("company", "date", "total")}
    tot_tp = sum(c[0] for c in counts.values())
    tot_fp = sum(c[1] for c in counts.values())
    tot_fn = sum(c[2] for c in counts.values())
    return {
        "documents": n_docs,
        "fields": fields,
        "overall_micro": prf_from_counts(tot_tp, tot_fp, tot_fn),
    }


def _fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def format_extraction_md(report: dict[str, Any]) -> str:
    lines = [
        "# NER-Style Extraction Precision, Recall, and F1",
        "",
        "Each normalized field and each 4-tuple line item `(description, quantity, unit_price, line_total)` is scored as one entity unit (a partially correct value is both 1 FP and 1 FN).",
        "",
    ]

    def add_table(title: str, data: dict[str, Any], field_order: tuple[str, ...]) -> None:
        lines.extend([
            f"## {title} ({data['documents']} documents)",
            "",
            "| Field | TP | FP | FN | Precision | Recall | F1 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for fname in field_order:
            s = data["fields"][fname]
            lines.append(
                f"| {fname} | {s['tp']} | {s['fp']} | {s['fn']} | {_fmt(s['precision'])} | {_fmt(s['recall'])} | {_fmt(s['f1'])} |"
            )
        ov = data["overall_micro"]
        lines.append(
            f"| **Overall (micro)** | **{ov['tp']}** | **{ov['fp']}** | **{ov['fn']}** | **{_fmt(ov['precision'])}** | **{_fmt(ov['recall'])}** | **{_fmt(ov['f1'])}** |"
        )
        lines.append("")

    for hname, hdata in report.get("held_out", {}).items():
        add_table(f"Held-out: {hname}", hdata, ALL_FIELDS)

    if report.get("dev_pooled"):
        add_table("Development pooled (cafe_01 + plumbing_01)", report["dev_pooled"], ALL_FIELDS)
    for dname, ddata in report.get("dev", {}).items():
        add_table(f"Development: {dname}", ddata, ALL_FIELDS)

    if report.get("sroie"):
        add_table("Real receipts: SROIE", report["sroie"], ("company", "date", "total"))

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", nargs="+", type=Path, default=DEFAULT_DEV)
    ap.add_argument("--held-out", nargs="+", type=Path, default=DEFAULT_HELDOUT)
    ap.add_argument("--sroie", type=Path, default=DEFAULT_SROIE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)

    held_out = {b.name: evaluate_bundle(b) for b in a.held_out}
    dev_list = [evaluate_bundle(b) for b in a.dev]
    dev = {d["bundle"]: d for d in dev_list}
    dev_pooled = pool_bundle_results(dev_list) if dev_list else None
    sroie = evaluate_sroie_jsonl(a.sroie) if a.sroie.exists() else None

    report = {
        "held_out": held_out,
        "dev": dev,
        "dev_pooled": dev_pooled,
        "sroie": sroie,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "extraction_metrics.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    md = format_extraction_md(report)
    (a.out / "extraction_metrics.md").write_text(md, encoding="utf-8")
    print(f"wrote {a.out / 'extraction_metrics.md'} and {a.out / 'extraction_metrics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
