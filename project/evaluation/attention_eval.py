"""Evaluate cashbooks.attention against independent ledger.json ground truth.

    cd project
    python evaluation/attention_eval.py

Writes evaluation/results/final/attention.md and attention.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from cashbooks.attention import ATTENTION_TYPES, AttentionItem, find_attention_items
from cashbooks.store.db import Store
from cashbooks.store.load_gold import load_gold

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_DEV = [PROJECT / "data" / "dev" / "cafe_01", PROJECT / "data" / "dev" / "plumbing_01"]
DEFAULT_HELDOUT = [PROJECT / "data" / "test" / "landscaping_01"]
DEFAULT_OUT = PROJECT / "evaluation" / "results" / "final"
ZERO = Decimal("0.00")


def _m(val: Any) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"))


def _derived_due(inv: dict) -> date:
    issue = date.fromisoformat(inv["issue_date"])
    m = re.search(r"\d+", inv.get("payment_terms") or "")
    days = int(m.group()) if m else 0
    return issue + timedelta(days=days)


def _stated_due(inv: dict) -> date | None:
    if inv.get("stated_due_date"):
        return date.fromisoformat(inv["stated_due_date"])
    if inv.get("print_due_date"):
        return _derived_due(inv)
    return None


def expected_attention_from_ledger(bundle: Path) -> set[tuple[str, str]]:
    """Derive expected (kind, subject) pairs directly from ledger.json without tools."""
    ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
    clock = date.fromisoformat(ledger["business"]["evaluation_clock"])
    vendors = {v["vendor_id"]: v for v in ledger["vendors"]}
    bank = {t["txn_id"]: t for t in ledger.get("bank", [])}
    credits = ledger.get("credits", [])
    payments = ledger.get("payments", [])

    paid_by_inv: dict[str, Decimal] = defaultdict(lambda: ZERO)
    pay_txns_by_inv: dict[str, list[str]] = defaultdict(list)
    linked_txns: set[str] = set()
    for p in payments:
        txn = bank.get(p["txn_id"])
        if txn and date.fromisoformat(txn["posted_on"]) <= clock:
            num = p["invoice_number"]
            paid_by_inv[num] += _m(p["amount_applied"])
            pay_txns_by_inv[num].append(p["txn_id"])
            linked_txns.add(p["txn_id"])

    cred_by_inv: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for c in credits:
        if date.fromisoformat(c["issued_on"]) <= clock:
            cred_by_inv[c["invoice_number"]] += _m(c["amount"])

    expected: set[tuple[str, str]] = set()
    seen_inv_keys: set[tuple] = set()

    for inv in ledger["invoices"]:
        if date.fromisoformat(inv["issue_date"]) > clock:
            continue
        num = inv["invoice_number"]
        total = _m(inv["total"])
        paid = paid_by_inv[num]
        cred = cred_by_inv[num]
        settled = paid + cred
        due = _stated_due(inv) or _derived_due(inv)

        # 1. overdue_bill
        if settled < total and due < clock:
            expected.add(("overdue_bill", num))

        # 2. duplicate_bill
        dup_key = (inv["vendor_id"], total, inv["issue_date"], inv.get("reference_or_po"))
        if inv.get("duplicate_of") or dup_key in seen_inv_keys:
            expected.add(("duplicate_bill", num))
        else:
            seen_inv_keys.add(dup_key)

        # 3. duplicate_payment
        if len(pay_txns_by_inv[num]) > 1 and paid > total:
            expected.add(("duplicate_payment", num))

        # 4. partial_payment
        if paid > ZERO and settled < total:
            expected.add(("partial_payment", num))

        # 7. bank_detail_mismatch
        vp = (vendors.get(inv["vendor_id"], {}).get("verified_payment") or {})
        remit = inv.get("remit") or {}
        if vp and remit:
            acct_diff = remit.get("account_number") and vp.get("account_number") and remit["account_number"] != vp["account_number"]
            rout_diff = remit.get("routing_number") and vp.get("routing_number") and remit["routing_number"] != vp["routing_number"]
            bank_diff = remit.get("bank_name") and vp.get("bank_name") and remit["bank_name"].strip().lower() != vp["bank_name"].strip().lower()
            if acct_diff or rout_diff or bank_diff:
                expected.add(("bank_detail_mismatch", num))

        # 8. total_mismatch
        planted = inv.get("planted") or {}
        lines = inv.get("lines") or []
        sub_ok = True
        if lines and inv.get("subtotal") is not None:
            sub_ok = sum((_m(ln["line_total"]) for ln in lines), ZERO) == _m(inv["subtotal"])
        tot_ok = True
        if inv.get("subtotal") is not None:
            tot_ok = _m(inv["subtotal"]) + _m(inv.get("tax") or "0.00") == total
        if planted.get("stated_total_mismatch") or not sub_ok or not tot_ok:
            expected.add(("total_mismatch", num))

        # 9. due_date_conflict
        stated = _stated_due(inv)
        derived = _derived_due(inv)
        if planted.get("due_date_conflict") or (stated is not None and stated != derived):
            expected.add(("due_date_conflict", num))

    # 10. message_conflict
    for m in ledger.get("messages", []):
        if m.get("kind") == "payment_claim":
            for ref in m.get("invoice_refs", []):
                inv = next((i for i in ledger["invoices"] if i["invoice_number"] == ref), None)
                if inv and (paid_by_inv[ref] + cred_by_inv[ref]) < _m(inv["total"]):
                    expected.add(("message_conflict", ref))

    # 6. unmatched_bank_debit
    for tid, txn in bank.items():
        if _m(txn["amount"]) < ZERO and date.fromisoformat(txn["posted_on"]) <= clock and tid not in linked_txns:
            expected.add(("unmatched_bank_debit", tid))

    return expected


def _score_sets(expected: set[tuple[str, str]], found: list[AttentionItem]) -> dict[str, Any]:
    found_set = {(it.kind, it.subject) for it in found}
    tp = expected & found_set
    missed = sorted(expected - found_set)
    spurious = sorted(found_set - expected)

    by_type: dict[str, dict[str, Any]] = {}
    for kind in ATTENTION_TYPES:
        e_k = {x for x in expected if x[0] == kind}
        f_k = {x for x in found_set if x[0] == kind}
        tp_k = e_k & f_k
        prec = round(len(tp_k) / len(f_k), 3) if f_k else None
        rec = round(len(tp_k) / len(e_k), 3) if e_k else None
        by_type[kind] = {
            "expected": len(e_k),
            "found": len(f_k),
            "tp": len(tp_k),
            "missed": [x[1] for x in sorted(e_k - f_k)],
            "spurious": [x[1] for x in sorted(f_k - e_k)],
            "precision": prec,
            "recall": rec,
        }

    prec_all = round(len(tp) / len(found_set), 3) if found_set else None
    rec_all = round(len(tp) / len(expected), 3) if expected else None
    return {
        "expected": len(expected),
        "found": len(found_set),
        "tp": len(tp),
        "missed": missed,
        "spurious": spurious,
        "precision": prec_all,
        "recall": rec_all,
        "by_type": by_type,
    }


def evaluate_bundles(
    dev_bundles: list[Path] | None = None,
    heldout_bundles: list[Path] | None = None,
) -> dict[str, Any]:
    dev_bundles = dev_bundles if dev_bundles is not None else DEFAULT_DEV
    heldout_bundles = heldout_bundles if heldout_bundles is not None else DEFAULT_HELDOUT

    report: dict[str, Any] = {"dev": {}, "held_out": {}}
    for split, bundles in (("dev", dev_bundles), ("held_out", heldout_bundles)):
        for b in bundles:
            ledger = json.loads((b / "ledger.json").read_text(encoding="utf-8"))
            biz_id = ledger["business"]["business_id"]
            clock = date.fromisoformat(ledger["business"]["evaluation_clock"])
            exp = expected_attention_from_ledger(b)

            gold_store, _ = load_gold(b)
            c4_items = find_attention_items(gold_store, clock)
            entry: dict[str, Any] = {"C4": _score_sets(exp, c4_items)}

            xdb = b / "extracted.sqlite"
            if xdb.exists():
                conn = sqlite3.connect(str(xdb))
                conn.row_factory = sqlite3.Row
                ext_store = Store(conn, biz_id)
                c3_items = find_attention_items(ext_store, clock)
                entry["C3"] = _score_sets(exp, c3_items)
                conn.close()
            else:
                entry["C3"] = None

            report[split][b.name] = entry
    return report


def format_attention_md(report: dict[str, Any]) -> str:
    lines = ["# Attention-Item Evaluation", ""]
    for split_title, split_key in (("Development bundles", "dev"), ("Held-out bundle", "held_out")):
        lines += [f"## {split_title}", ""]
        lines += [
            "| Bundle | Store | Expected | Found | TP | Missed | Spurious | Precision | Recall |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for bname, stores in report[split_key].items():
            for sname in ("C3", "C4"):
                sc = stores.get(sname)
                if sc is None:
                    lines.append(f"| {bname} | {sname} | — | n/a (no extracted.sqlite) | — | — | — | — | — |")
                    continue
                p_str = "n/a" if sc["precision"] is None else f"{sc['precision']:.1%}"
                r_str = "n/a" if sc["recall"] is None else f"{sc['recall']:.1%}"
                lines.append(
                    f"| {bname} | {sname} | {sc['expected']} | {sc['found']} | {sc['tp']} | "
                    f"{len(sc['missed'])} | {len(sc['spurious'])} | {p_str} | {r_str} |"
                )
        lines.append("")

        for bname, stores in report[split_key].items():
            for sname in ("C3", "C4"):
                sc = stores.get(sname)
                if sc is None:
                    continue
                lines += [
                    f"### {bname} ({sname}) by item type",
                    "",
                    "| Item type | Expected | Found | Missed | Spurious | Precision | Recall |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                ]
                for kind in ATTENTION_TYPES:
                    t = sc["by_type"][kind]
                    if t["expected"] == 0 and t["found"] == 0:
                        continue
                    p_str = "n/a" if t["precision"] is None else f"{t['precision']:.0%}"
                    r_str = "n/a" if t["recall"] is None else f"{t['recall']:.0%}"
                    m_str = ", ".join(t["missed"]) or "—"
                    sp_str = ", ".join(t["spurious"]) or "—"
                    lines.append(
                        f"| {kind} | {t['expected']} | {t['found']} | {m_str} | {sp_str} | {p_str} | {r_str} |"
                    )
                lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)

    rep = evaluate_bundles()
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "attention.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    md = format_attention_md(rep)
    (a.out / "attention.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {a.out / 'attention.md'} and {a.out / 'attention.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
