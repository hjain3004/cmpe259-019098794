"""Phase 1 vertical slice on one bundle, no LLM calls.

1. Load the bundle's gold records into SQLite (the C4 database).
2. Answer five owner questions with the deterministic tools and check them
   against the values the scenario was built to produce.
3. Run C1's BM25 retrieval on ten questions and report recall@k against the
   chunks that hold the answer.

    cd project && python evaluation/run_slice.py data/dev/cafe_01 [--k 8]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from cashbooks.contracts.tools import GetBillStatusArgs, ListOpenBillsArgs
from cashbooks.store.db import connect
from cashbooks.store.load_gold import load_gold
from cashbooks.tools.bills import get_bill_status, list_open_bills

CLOCK = date(2026, 9, 24)

# Chunks that contain the answer, using C1's chunk-ID scheme.
RETRIEVAL_GOLD: list[tuple[str, str, list[str]]] = [
    ("Q02", "How much do I owe Northside Supplies as of September 30?",
     ["span_inv_NS-1062_p1", "span_inv_NS-1070_p1", "span_cn_CN-0457_p1"]),
    ("Q04", "Did I already pay invoice NS-1048?", ["span_inv_NS-1048_p1", "txn_0193"]),
    ("Q06", "What remains unpaid on GP-228 after the partial payment?", ["span_inv_GP-228_p1", "txn_0181"]),
    ("Q08", "Show me where the total for NS-1048 came from.", ["span_inv_NS-1048_p1"]),
    ("Q09", "What invoice matches the $842 bank payment on September 12?", ["txn_0193", "span_inv_NS-1048_p1"]),
    ("Q10", "Did I pay any invoice twice?", ["txn_0102", "txn_0109"]),
    ("Q11", "Is Northside Supply Co. the same vendor as Northside Supplies?", ["vh_v_northside"]),
    ("Q12", "Did the payment details on BW-771 change?", ["span_inv_BW-771_p1", "vh_v_beanworks"]),
    ("Q13", "Is the amount on BW-771 unusual for this vendor?", ["span_inv_BW-771_p1", "span_inv_BW-760_p1"]),
    ("Q30", "What was the $1,750 payment on my bank statement for?", ["txn_0205"]),
]


def tool_checks(store) -> list[tuple[str, str, bool, str]]:
    """(query id, question, passed, what the tools returned)."""
    out = []

    r = list_open_bills(store, ListOpenBillsArgs(as_of=CLOCK, due_before=date(2026, 10, 1)))
    upcoming = [b.invoice_number for b in r.bills if b.due_date and b.due_date >= CLOCK]
    out.append(("Q01", "Bills due in the next seven days",
                upcoming == ["NS-1062"], f"due 2026-09-24..2026-10-01: {upcoming}"))

    r = list_open_bills(store, ListOpenBillsArgs(as_of=date(2026, 9, 30), vendor="Northside Supplies"))
    total = sum((b.remaining.amount for b in r.bills), Decimal("0"))
    out.append(("Q02", "Owed to Northside as of 2026-09-30",
                total == Decimal("1462.85"), f"{total} USD from {[b.invoice_number for b in r.bills]}"))

    r = list_open_bills(store, ListOpenBillsArgs(as_of=CLOCK))
    overdue = [b.invoice_number for b in r.bills if b.overdue]
    out.append(("Q03", "Overdue invoices", overdue == ["GP-221", "GP-228"], f"{overdue}"))

    s = get_bill_status(store, GetBillStatusArgs(invoice_number="NS-1048", as_of=CLOCK))
    out.append(("Q04", "Is NS-1048 paid?", s.bill.state.value == "paid",
                f"{s.bill.state.value} via {[p.txn_id for p in s.payments]}"))

    s = get_bill_status(store, GetBillStatusArgs(invoice_number="GP-228", as_of=CLOCK))
    out.append(("Q06", "Remaining on GP-228", s.bill.remaining.amount == Decimal("212.30"),
                f"{s.bill.remaining.amount} USD; conflicting claims {s.conflicting_claims}"))
    return out


def retrieval_checks(bundle: Path, k: int) -> list[tuple[str, float | None, list[str]]] | None:
    try:
        from cashbooks.configs.c1_rag import C1Retriever, recall_at_k
    except ImportError:
        return None
    retriever = C1Retriever(bundle)
    rows = []
    for qid, question, gold in RETRIEVAL_GOLD:
        got = [c.chunk_id for c in retriever.search(question, k=k)]
        rows.append((qid, recall_at_k(got, gold), [g for g in gold if g not in got]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--out", type=Path, help="write results as JSON")
    a = ap.parse_args()

    db = a.bundle / "gold.sqlite"
    if db.exists():
        db.unlink()
    store, report = load_gold(a.bundle, connect(db))
    print(f"Loaded {store.business_id}: {report}\n")

    print("Deterministic tools")
    checks = tool_checks(store)
    for qid, q, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {qid}  {q}: {detail}")
    passed = sum(ok for _, _, ok, _ in checks)
    print(f"  {passed}/{len(checks)} passed\n")

    print(f"C1 BM25 retrieval, recall@{a.k}")
    rows = retrieval_checks(a.bundle, a.k)
    if rows is None:
        print("  skipped: cashbooks.configs.c1_rag not present yet")
    else:
        for qid, rec, missed in rows:
            miss = f"  missed {missed}" if missed else ""
            print(f"  {qid}  {rec:.2f}{miss}" if rec is not None else f"  {qid}  n/a")
        vals = [r for _, r, _ in rows if r is not None]
        print(f"  mean recall@{a.k}: {sum(vals) / len(vals):.2f}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({
            "bundle": str(a.bundle), "load": report.counts, "ungrounded": report.ungrounded,
            "tools": [{"query": q, "passed": ok, "detail": d} for q, _, ok, d in checks],
            "retrieval": None if rows is None else [{"query": q, "recall": r, "missed": m} for q, r, m in rows],
        }, indent=2))
    return 0 if passed == len(checks) and not report.ungrounded else 1


if __name__ == "__main__":
    sys.exit(main())
