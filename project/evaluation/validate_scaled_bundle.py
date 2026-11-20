"""Offline integrity and gold-invariance validator for scaled synthetic bundles.

Checks a scaled bundle against its base bundle (e.g. data/dev/cafe_01), distinguishing:
  - Category A (fatal): identifier/filename collisions, overwritten files, arithmetic or
    date violations, broken references, forbidden-amount collisions, or changes to
    ledger-truth gold answers across Q01-Q30.
  - Category B (diagnosed limitation): deterministic matching (`link_payments` used by
    extracted-record linking and `load_gold`) failing to confirm historical paid bills
    when added invoices share identical dollar amounts within overlapping 45-day windows
    and bank descriptors omit invoice numbers.

    cd project
    python evaluation/validate_scaled_bundle.py data/dev/cafe_01 data/dev/cafe_01_x32
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

PROJECT = Path(__file__).resolve().parents[1]
DATA_GEN = PROJECT / "data" / "generator"
if str(DATA_GEN) not in sys.path:
    sys.path.insert(0, str(DATA_GEN))

from check_gold import LedgerModel, _effective_due, check_bundle as check_gold_bundle  # noqa: E402
from render import validate_ledger  # noqa: E402
from scale_bundle import FORBIDDEN_AMOUNTS  # noqa: E402

from cashbooks.contracts.tools import (  # noqa: E402
    CompareVendorPaymentDetailsArgs,
    GetBillStatusArgs,
    ListOpenBillsArgs,
    MatchPaymentsArgs,
    SumAmountDueArgs,
    SummarizePurchasesArgs,
)
from cashbooks.normalize.vendors import resolve_vendor  # noqa: E402
from cashbooks.store.load_gold import load_gold  # noqa: E402
from cashbooks.tools.bills import get_bill_status, list_open_bills  # noqa: E402
from cashbooks.tools.matching import descriptor_vendor  # noqa: E402
from cashbooks.tools.more import (  # noqa: E402
    compare_vendor_payment_details,
    match_payments,
    sum_amount_due,
    summarize_purchases,
)
from cashbooks.tools.status import compute_state  # noqa: E402
from cashbooks.tools.more import (  # noqa: E402
    compare_vendor_payment_details,
    match_payments,
    sum_amount_due,
    summarize_purchases,
)
from cashbooks.tools.status import compute_state  # noqa: E402

ZERO = Decimal("0.00")
HISTORICAL_CUTOFF = date(2026, 7, 1)


def _dec(val: Any) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_structural_and_ledger_invariants(
    base_bundle: Path,
    scaled_bundle: Path,
    check_rendered_files: bool = True,
) -> dict[str, Any]:
    """Run Category A structural, reference, arithmetic, date, forbidden-amount, and gold checks."""
    base_led = json.loads((base_bundle / "ledger.json").read_text(encoding="utf-8"))
    sc_led = json.loads((scaled_bundle / "ledger.json").read_text(encoding="utf-8"))
    errors: list[str] = []

    # 1. Basic ledger validation from render.py
    try:
        validate_ledger(sc_led)
    except Exception as exc:
        errors.append(f"validate_ledger failed: {exc}")

    # 2. Identifier uniqueness (invoices, vendor+invoice, txns, msgs, credits, PO refs)
    inv_nums = [i["invoice_number"] for i in sc_led["invoices"]]
    dup_invs = sorted([k for k, c in Counter(inv_nums).items() if c > 1])
    if dup_invs:
        errors.append(f"duplicate invoice_numbers: {dup_invs}")

    vk = [(i["vendor_id"], i["invoice_number"]) for i in sc_led["invoices"]]
    dup_vk = sorted([k for k, c in Counter(vk).items() if c > 1])
    if dup_vk:
        errors.append(f"duplicate (vendor_id, invoice_number): {dup_vk}")

    txn_ids = [t["txn_id"] for t in sc_led["bank"]]
    dup_txns = sorted([k for k, c in Counter(txn_ids).items() if c > 1])
    if dup_txns:
        errors.append(f"duplicate txn_ids: {dup_txns}")

    msg_ids = [m["msg_id"] for m in sc_led.get("messages", [])]
    dup_msgs = sorted([k for k, c in Counter(msg_ids).items() if c > 1])
    if dup_msgs:
        errors.append(f"duplicate msg_ids: {dup_msgs}")

    cr_ids = [c["credit_id"] for c in sc_led.get("credits", [])]
    dup_crs = sorted([k for k, c in Counter(cr_ids).items() if c > 1])
    if dup_crs:
        errors.append(f"duplicate credit_ids: {dup_crs}")

    po_refs = [i["reference_or_po"] for i in sc_led["invoices"] if i.get("reference_or_po")]
    dup_pos = sorted([k for k, c in Counter(po_refs).items() if c > 1])
    if dup_pos:
        errors.append(f"duplicate reference_or_po: {dup_pos}")

    # 3. Document filename integrity on disk (no overwrites or missing PDFs / manifests)
    inv_counts = Counter(inv_nums)
    expected_stems = [
        n if inv_counts[n] == 1 else f"{n}--{i['vendor_id'].removeprefix('v_')}"
        for i, n in zip(sc_led["invoices"], inv_nums)
    ]
    dup_stems = sorted([k for k, c in Counter(expected_stems).items() if c > 1])
    if dup_stems:
        errors.append(f"duplicate document stems causing PDF overwrites: {dup_stems}")

    if check_rendered_files:
        inv_dir = scaled_bundle / "invoices"
        if not inv_dir.exists():
            errors.append("missing rendered invoices/ directory")
        else:
            pdfs = sorted(inv_dir.glob("*.pdf"))
            mfs = sorted(inv_dir.glob("*.fields.json"))
            if len(pdfs) != len(sc_led["invoices"]) or len(mfs) != len(sc_led["invoices"]):
                errors.append(
                    f"rendered file count mismatch: {len(pdfs)} pdfs, {len(mfs)} manifests vs {len(sc_led['invoices'])} invoices"
                )
            for stem in expected_stems:
                if not (inv_dir / f"{stem}.pdf").exists():
                    errors.append(f"missing rendered PDF: invoices/{stem}.pdf")
                if not (inv_dir / f"{stem}.fields.json").exists():
                    errors.append(f"missing rendered manifest: invoices/{stem}.fields.json")
        if not (scaled_bundle / "bank.csv").exists():
            errors.append("missing bank.csv")
        if not (scaled_bundle / "messages.jsonl").exists():
            errors.append("missing messages.jsonl")
        if not (scaled_bundle / "vendor_history.json").exists():
            errors.append("missing vendor_history.json")

    # 4. Original records preserved verbatim
    if sc_led["vendors"] != base_led["vendors"]:
        errors.append("vendors modified relative to base ledger")
    if sc_led.get("credits", []) != base_led.get("credits", []):
        errors.append("credits modified relative to base ledger")
    if sc_led["business"] != base_led["business"]:
        errors.append("business metadata modified relative to base ledger")

    sc_inv_map = {i["invoice_number"]: i for i in sc_led["invoices"]}
    base_inv_nums = set()
    for bi in base_led["invoices"]:
        n = bi["invoice_number"]
        base_inv_nums.add(n)
        if sc_inv_map.get(n) != bi:
            errors.append(f"base invoice {n} missing or modified")

    sc_bank_map = {t["txn_id"]: t for t in sc_led["bank"]}
    base_txn_ids = set()
    for bt in base_led["bank"]:
        tid = bt["txn_id"]
        base_txn_ids.add(tid)
        if sc_bank_map.get(tid) != bt:
            errors.append(f"base bank row {tid} missing or modified")

    sc_msg_map = {m["msg_id"]: m for m in sc_led.get("messages", [])}
    base_msg_ids = set()
    for bm in base_led.get("messages", []):
        mid = bm["msg_id"]
        base_msg_ids.add(mid)
        if sc_msg_map.get(mid) != bm:
            errors.append(f"base message {mid} missing or modified")

    base_pay_keys = {(p["txn_id"], p["invoice_number"], p["amount_applied"]) for p in base_led.get("payments", [])}
    sc_pay_keys = {(p["txn_id"], p["invoice_number"], p["amount_applied"]) for p in sc_led.get("payments", [])}
    if not base_pay_keys.issubset(sc_pay_keys):
        errors.append("base payment links missing or modified")

    # 5. Referential integrity across added messages & payments
    valid_inv_set = set(inv_nums)
    for m in sc_led.get("messages", []):
        for ref in m.get("invoice_refs", []):
            if ref not in valid_inv_set:
                errors.append(f"message {m['msg_id']} references unknown invoice {ref}")
        if m["msg_id"] not in base_msg_ids:
            if date.fromisoformat(m["received_on"]) >= HISTORICAL_CUTOFF:
                errors.append(f"added message {m['msg_id']} received_on {m['received_on']} >= {HISTORICAL_CUTOFF}")

    paid_txns = {p["txn_id"]: p for p in sc_led.get("payments", [])}
    for inv in sc_led["invoices"]:
        num = inv["invoice_number"]
        if num in base_inv_nums:
            continue
        iss = date.fromisoformat(inv["issue_date"])
        if iss >= HISTORICAL_CUTOFF:
            errors.append(f"added invoice {num} issue_date {iss} >= {HISTORICAL_CUTOFF}")
        tot = _dec(inv["total"])
        if tot in FORBIDDEN_AMOUNTS:
            errors.append(f"added invoice {num} total {tot} collides with FORBIDDEN_AMOUNTS")
        p_rows = [p for p in sc_led.get("payments", []) if p["invoice_number"] == num]
        if len(p_rows) != 1 or _dec(p_rows[0]["amount_applied"]) != tot:
            errors.append(f"added invoice {num} is not linked to exact single full payment")
        else:
            tx = sc_bank_map.get(p_rows[0]["txn_id"])
            if not tx:
                errors.append(f"added payment for {num} missing bank row {p_rows[0]['txn_id']}")
            else:
                posted = date.fromisoformat(tx["posted_on"])
                if posted >= HISTORICAL_CUTOFF:
                    errors.append(f"added payment {tx['txn_id']} posted_on {posted} >= {HISTORICAL_CUTOFF}")
                if posted < iss:
                    errors.append(f"added payment {tx['txn_id']} posted_on {posted} < issue_date {iss}")

    for bt in sc_led["bank"]:
        tid = bt["txn_id"]
        if tid in base_txn_ids or tid in paid_txns:
            continue
        if date.fromisoformat(bt["posted_on"]) >= HISTORICAL_CUTOFF:
            errors.append(f"added unlinked bank row {tid} posted_on {bt['posted_on']} >= {HISTORICAL_CUTOFF}")
        amt = abs(_dec(bt["amount"]))
        if amt in FORBIDDEN_AMOUNTS:
            errors.append(f"added unlinked bank row {tid} amount {amt} collides with FORBIDDEN_AMOUNTS")

    # 6. gold.yaml preserved and passes check_gold.py
    if (base_bundle / "gold.yaml").exists() and (scaled_bundle / "gold.yaml").exists():
        if (base_bundle / "gold.yaml").read_bytes() != (scaled_bundle / "gold.yaml").read_bytes():
            errors.append("gold.yaml differs from base bundle")
    try:
        cg_errs = check_gold_bundle(scaled_bundle)
        errors.extend(cg_errs)
    except Exception as exc:
        errors.append(f"check_gold raised {exc}")

    # 7. Central invariant against base ledger & queries.yaml (Category A)
    base_m = LedgerModel(base_bundle)
    sc_m = LedgerModel(scaled_bundle)
    invariance_checks = _check_ledger_gold_invariance(base_m, sc_m, errors)

    return {
        "counts": {
            "invoices": len(sc_led["invoices"]),
            "credits": len(sc_led.get("credits", [])),
            "messages": len(sc_led.get("messages", [])),
            "bank_rows": len(sc_led["bank"]),
            "payments": len(sc_led.get("payments", [])),
            "vendors": len(sc_led["vendors"]),
        },
        "unique_checks": {
            "duplicate_invoices": dup_invs,
            "duplicate_vendor_invoice": dup_vk,
            "duplicate_txns": dup_txns,
            "duplicate_messages": dup_msgs,
            "duplicate_credits": dup_crs,
            "duplicate_po_refs": dup_pos,
            "duplicate_doc_stems": dup_stems,
        },
        "invariance_checks": invariance_checks,
        "errors": errors,
    }


def _check_ledger_gold_invariance(
    base_m: LedgerModel,
    sc_m: LedgerModel,
    errors: list[str],
) -> dict[str, Any]:
    """Compare pure-ledger answers across Q01-Q30 query invariants between base and scaled."""
    clock = base_m.clock

    def open_summary(m: LedgerModel, as_of: date | None = None, vendor_id: str | None = None) -> list[tuple[str, str]]:
        out = []
        for num in m.non_duplicate_invoices():
            inv = m.invoices[num]
            if vendor_id and inv["vendor_id"] != vendor_id:
                continue
            if date.fromisoformat(inv["issue_date"]) > (as_of or clock):
                continue
            rem = m.remaining_ledger(num)
            if rem > ZERO:
                out.append((num, f"{rem:.2f}"))
        return sorted(out)

    base_open = open_summary(base_m)
    sc_open = open_summary(sc_m)
    if base_open != sc_open:
        errors.append(f"outstanding bills changed: base={base_open} scaled={sc_open}")

    # Q02 / Q16 / Q19: Northside owed as of clock & 2026-09-30, plus overdue Northside
    base_ns = open_summary(base_m, date(2026, 9, 30), vendor_id="v_northside")
    sc_ns = open_summary(sc_m, date(2026, 9, 30), vendor_id="v_northside")
    if base_ns != sc_ns:
        errors.append(f"Northside open bills changed: base={base_ns} scaled={sc_ns}")

    base_overdue = sorted(n for n in base_m.non_duplicate_invoices() if base_m.is_overdue(n))
    sc_overdue = sorted(n for n in sc_m.non_duplicate_invoices() if sc_m.is_overdue(n))
    if base_overdue != sc_overdue:
        errors.append(f"overdue bills changed: base={base_overdue} scaled={sc_overdue}")

    # Q01: 7-day due window (2026-09-24 .. 2026-10-01)
    win_end = clock + timedelta(days=7)
    base_due7 = sorted(n for n, _ in base_open if clock <= _effective_due(base_m.invoices[n]) <= win_end)
    sc_due7 = sorted(n for n, _ in sc_open if clock <= _effective_due(sc_m.invoices[n]) <= win_end)
    if base_due7 != sc_due7:
        errors.append(f"7-day due window changed: base={base_due7} scaled={sc_due7}")

    # Q10: Duplicate/overpaid invoices
    base_overpaid = sorted(n for n in base_m.invoices if base_m.status_ledger(n) == "overpaid")
    sc_overpaid = sorted(n for n in sc_m.invoices if sc_m.status_ledger(n) == "overpaid")
    if base_overpaid != sc_overpaid:
        errors.append(f"overpaid bills changed: base={base_overpaid} scaled={sc_overpaid}")

    # Q07 / Q12 / Q18: Vendor bank-detail mismatch invoices
    def mismatch_bills(m: LedgerModel) -> list[str]:
        bad = []
        for n, inv in m.invoices.items():
            vp = m.vendors[inv["vendor_id"]]["verified_payment"]
            rm = inv["remit"]
            if rm["account_number"] != vp["account_number"] or rm["routing_number"] != vp["routing_number"]:
                bad.append(n)
        return sorted(bad)

    base_mm = mismatch_bills(base_m)
    sc_mm = mismatch_bills(sc_m)
    if base_mm != sc_mm:
        errors.append(f"bank-detail mismatch bills changed: base={base_mm} scaled={sc_mm}")

    # Q14 / Q15: August purchases & 5-lb bags (2026-08-01 .. 2026-08-31)
    def august_coffee_stats(m: LedgerModel) -> tuple[str, int]:
        spend = ZERO
        bags5 = 0
        for inv in m.invoices.values():
            iss = date.fromisoformat(inv["issue_date"])
            if not (date(2026, 8, 1) <= iss <= date(2026, 8, 31)):
                continue
            for ln in inv["lines"]:
                desc = ln["description"].lower()
                if "espresso" in desc or "coffee" in desc or "blend" in desc or "ethiopia" in desc:
                    spend += _dec(ln["line_total"])
                if "5 lb" in desc or "five" in desc:
                    bags5 += int(_dec(ln["quantity"]))
        return f"{spend:.2f}", bags5

    if august_coffee_stats(base_m) != august_coffee_stats(sc_m):
        errors.append(f"August purchase stats changed: {august_coffee_stats(base_m)} vs {august_coffee_stats(sc_m)}")

    # Q13: BeanWorks immediate predecessor to BW-771 and max prior BeanWorks total
    sc_bw = sorted(
        (inv["issue_date"], inv["invoice_number"], _dec(inv["total"]))
        for inv in sc_m.invoices.values()
        if inv["vendor_id"] == "v_beanworks" and inv["invoice_number"] != "BW-771"
    )
    prev_bw = sc_bw[-1] if sc_bw else None
    max_prior_bw = max((x[2] for x in sc_bw), default=ZERO)
    bw771_tot = _dec(sc_m.invoices["BW-771"]["total"])
    if not prev_bw or prev_bw[1] != "BW-760" or max_prior_bw >= bw771_tot:
        errors.append(f"Q13 BeanWorks precedent invariant broken: prev={prev_bw}, max_prior={max_prior_bw}, BW-771={bw771_tot}")

    # Q17: Greenway open/post-July bills
    sc_gp_open = open_summary(sc_m, vendor_id="v_greenway")
    if [x[0] for x in sc_gp_open] != ["GP-221", "GP-228"]:
        errors.append(f"Q17 Greenway open bills changed: {sc_gp_open}")

    return {
        "open_bills": sc_open,
        "overdue_bills": sc_overdue,
        "due_7d_bills": base_due7,
        "northside_open": sc_ns,
        "overpaid_bills": sc_overpaid,
        "bank_mismatch_bills": sc_mm,
        "august_coffee": {"spend": august_coffee_stats(sc_m)[0], "five_lb_bags": august_coffee_stats(sc_m)[1]},
        "bw771_immediate_prior": {"issue_date": prev_bw[0], "invoice": prev_bw[1], "total": f"{prev_bw[2]:.2f}"} if prev_bw else None,
        "bw_min_max_prior": {"min": f"{min(x[2] for x in sc_bw):.2f}", "max": f"{max_prior_bw:.2f}"} if sc_bw else None,
        "greenway_open": sc_gp_open,
    }


def classify_observable_collisions(scaled_bundle: Path) -> dict[str, Any]:
    """Classify matcher-unconfirmed historical bills strictly from observable documents (no payments peeking).

    Buckets:
      - unique_local: bill has an invoice-number match or unique (vendor, amount, window) match.
      - unique_joint: ambiguous locally, but uniquely forced via iterative degree-1 elimination (joint assignment).
      - not_identifiable: remains in a cycle / symmetric component with multiple valid bill-to-txn assignments.
    """
    as_of = date(2026, 9, 24)
    sc_gs, _ = load_gold(scaled_bundle)
    vendor_dicts = sc_gs.vendor_dicts()

    unconf = sorted(
        (
            b for b in sc_gs.bills()
            if b.issue_date < HISTORICAL_CUTOFF
            and (compute_state(sc_gs, b, as_of).remaining > ZERO or len(compute_state(sc_gs, b, as_of).possible_payments) > 0)
        ),
        key=lambda b: b.invoice_number,
    )
    if not unconf:
        return {"unconfirmed_total": 0, "unique_local": [], "unique_joint": [], "not_identifiable": []}

    hist_bills = [b for b in sc_gs.bills() if b.issue_date < HISTORICAL_CUTOFF]
    hist_txns = [t for t in sc_gs.txns() if t.posted_on < HISTORICAL_CUTOFF and t.amount < ZERO]

    # Build vendor-scoped observable bipartite graph purely from invoices + bank descriptors/amounts/windows.
    bill_adj: dict[str, set[str]] = {}
    txn_adj: dict[str, set[str]] = defaultdict(set)
    for b in hist_bills:
        due = b.due_date or b.issue_date
        hi = due + timedelta(days=45)
        bset: set[str] = set()
        for t in hist_txns:
            if t.currency == b.currency and -t.amount == b.total and (b.issue_date <= t.posted_on <= hi):
                if descriptor_vendor(t.descriptor, vendor_dicts) == b.vendor_id:
                    bset.add(t.txn_id)
                    txn_adj[t.txn_id].add(b.invoice_number)
        bill_adj[b.invoice_number] = bset

    assigned: dict[str, tuple[str, str]] = {}
    used_txns: set[str] = set()
    for bn, ts in sorted(bill_adj.items()):
        if len(ts) == 1:
            tid = next(iter(ts))
            if len(txn_adj[tid]) == 1:
                assigned[bn] = (tid, "unique_local")
                used_txns.add(tid)

    changed = True
    while changed:
        changed = False
        for bn, ts in sorted(bill_adj.items()):
            if bn in assigned:
                continue
            rem_t = [t for t in ts if t not in used_txns]
            if len(rem_t) == 1:
                tid = rem_t[0]
                assigned[bn] = (tid, "unique_joint")
                used_txns.add(tid)
                changed = True
                break
        if changed:
            continue
        for tid, bs in sorted(txn_adj.items()):
            if tid in used_txns:
                continue
            rem_b = [bn for bn in bs if bn not in assigned]
            if len(rem_b) == 1:
                bn = rem_b[0]
                assigned[bn] = (tid, "unique_joint")
                used_txns.add(tid)
                changed = True
                break

    unique_local: list[dict[str, Any]] = []
    unique_joint: list[dict[str, Any]] = []
    not_identifiable: list[dict[str, Any]] = []
    for b in unconf:
        bn = b.invoice_number
        if bn in assigned:
            tid, kind = assigned[bn]
            rec = {
                "invoice": bn,
                "vendor_id": b.vendor_id,
                "total": f"{b.total:.2f}",
                "forced_txn": tid,
                "vendor_txns": sorted(bill_adj[bn]),
            }
            if kind == "unique_local":
                unique_local.append(rec)
            else:
                unique_joint.append(rec)
        else:
            not_identifiable.append({
                "invoice": bn,
                "vendor_id": b.vendor_id,
                "total": f"{b.total:.2f}",
                "vendor_txns": sorted(bill_adj[bn]),
            })

    return {
        "unconfirmed_total": len(unconf),
        "unique_local": unique_local,
        "unique_joint": unique_joint,
        "not_identifiable": not_identifiable,
    }


def check_matcher_invariance(base_bundle: Path, scaled_bundle: Path) -> dict[str, Any]:
    """Run in-memory load_gold + tool queries to separate Category B matcher limitations from Category A."""
    as_of = date(2026, 9, 24)
    base_gs, _ = load_gold(base_bundle)
    sc_gs, _ = load_gold(scaled_bundle)

    # Historical bills left unpaid/partial or without exact 1 confirmed link in load_gold
    false_open_hist = []
    by_vendor: Counter[str] = Counter()
    for bill in sc_gs.bills():
        if bill.issue_date >= HISTORICAL_CUTOFF:
            continue
        st = compute_state(sc_gs, bill, as_of)
        if st.remaining > ZERO or len(st.possible_payments) > 0 or len(st.payments) != 1:
            false_open_hist.append({
                "invoice": bill.invoice_number,
                "vendor_id": bill.vendor_id,
                "issue_date": bill.issue_date.isoformat(),
                "total": f"{bill.total:.2f}",
                "remaining_in_store": f"{st.remaining:.2f}",
                "confirmed_links": len(st.payments),
                "candidate_links": len(st.possible_payments),
            })
            by_vendor[bill.vendor_id] += 1

    def tool_snapshot(gs) -> dict[str, Any]:
        open_all = [(b.invoice_number, f"{b.remaining.amount:.2f}", b.overdue)
                    for b in list_open_bills(gs, ListOpenBillsArgs(as_of=as_of)).bills]
        due_7d = [(b.invoice_number, f"{b.remaining.amount:.2f}")
                  for b in list_open_bills(gs, ListOpenBillsArgs(as_of=as_of, due_before=as_of + timedelta(days=7))).bills]
        ns_sep30 = [(f"{m.amount:.2f}", m.currency)
                    for m in sum_amount_due(gs, SumAmountDueArgs(as_of=date(2026, 9, 30), vendor="Northside Supplies")).totals]
        ns_open = [(b.invoice_number, f"{b.remaining.amount:.2f}")
                   for b in list_open_bills(gs, ListOpenBillsArgs(as_of=as_of, vendor="Northside Supplies")).bills]
        ns_over = [(f"{m.amount:.2f}", m.currency)
                   for m in sum_amount_due(gs, SumAmountDueArgs(as_of=as_of, vendor="Northside Supplies", overdue_only=True)).totals]
        gp_open = [(b.invoice_number, f"{b.remaining.amount:.2f}")
                   for b in list_open_bills(gs, ListOpenBillsArgs(as_of=as_of, vendor="Greenway Produce")).bills]
        m842 = [(c.invoice_number, c.link_status)
                for c in match_payments(gs, MatchPaymentsArgs(amount=Decimal("842.00"), posted_on=date(2026, 9, 12))).candidates]
        m1750 = match_payments(gs, MatchPaymentsArgs(amount=Decimal("1750.00"), posted_on=date(2026, 9, 18))).outcome
        bw_cmp = compare_vendor_payment_details(gs, CompareVendorPaymentDetailsArgs(invoice_number="BW-771")).outcome
        ns_alias = sorted(c.vendor_id for c in resolve_vendor("Northside Supply Co.", gs.vendor_dicts()))
        q14 = [(f"{m.amount:.2f}", m.currency)
               for m in summarize_purchases(gs, SummarizePurchasesArgs(item="coffee", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31))).spend]
        q15 = [(q.unit, f"{q.quantity:.2f}")
               for q in summarize_purchases(gs, SummarizePurchasesArgs(item="5 lb bag", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31))).quantities]
        ns1048_res = get_bill_status(gs, GetBillStatusArgs(invoice_number="NS-1048", as_of=as_of))
        ns1048_tot = f"{ns1048_res.bill.total.amount:.2f}/{ns1048_res.subtotal.amount:.2f}/{ns1048_res.tax.amount:.2f}"
        gp221_st = get_bill_status(gs, GetBillStatusArgs(invoice_number="GP-221", as_of=as_of)).bill.state.value
        gp228_st = get_bill_status(gs, GetBillStatusArgs(invoice_number="GP-228", as_of=as_of))
        gp228_rem_cand = f"{gp228_st.remaining_if_candidates_apply.amount:.2f}" if gp228_st.remaining_if_candidates_apply else None
        ns1031_res = get_bill_status(gs, GetBillStatusArgs(invoice_number="NS-1031", as_of=as_of))
        ns1031_pmts = (len(ns1031_res.payments), len(ns1031_res.possible_payments))
        bw_all = sorted(
            (b.issue_date.isoformat(), b.invoice_number, b.total.amount)
            for b in list_open_bills(gs, ListOpenBillsArgs(as_of=as_of, vendor="BeanWorks", include_settled=True)).bills
            if b.invoice_number != "BW-771"
        )
        prev_bw = bw_all[-1][1] if bw_all else None
        prev_bw_tot = f"{bw_all[-1][2]:.2f}" if bw_all else None
        bw_lt_771 = all(x[2] < Decimal("1962.00") for x in bw_all)
        return {
            "q01_due_7d": due_7d,
            "list_open_bills": open_all,
            "q02_northside_sep30": ns_sep30,
            "q16_northside_open": ns_open,
            "q19_northside_overdue": ns_over,
            "q17_greenway_open": gp_open,
            "q04_ns1048_state": ns1048_res.bill.state.value,
            "q08_ns1048_sub_tax": ns1048_tot,
            "q06_gp228_if_cands_apply": gp228_rem_cand,
            "q09_match_842": m842,
            "q10_ns1031_links": ns1031_pmts,
            "q11_northside_alias": ns_alias,
            "q12_q18_bw771_mismatch": bw_cmp,
            "q13_bw771_immediate_prior": (prev_bw, prev_bw_tot, bw_lt_771),
            "q14_aug_coffee": q14,
            "q15_aug_5lb_bags": q15,
            "q17_gp221_state": gp221_st,
            "q30_match_1750_outcome": m1750,
        }

    base_tools = tool_snapshot(base_gs)
    sc_tools = tool_snapshot(sc_gs)
    tool_diffs = {
        k: {"base": base_tools[k], "scaled": sc_tools[k]}
        for k in base_tools
        if base_tools[k] != sc_tools[k]
    }

    def bw_range(gs) -> dict[str, Any]:
        bw_all = [
            b for b in list_open_bills(gs, ListOpenBillsArgs(as_of=as_of, vendor="BeanWorks", include_settled=True)).bills
            if b.invoice_number != "BW-771"
        ]
        tots = [b.total.amount for b in bw_all]
        return {"count": len(bw_all), "min": f"{min(tots):.2f}", "max": f"{max(tots):.2f}"} if tots else {"count": 0}

    return {
        "false_open_historical_count": len(false_open_hist),
        "false_open_by_vendor": dict(by_vendor),
        "false_open_sample": false_open_hist[:10],
        "tool_diffs_vs_base": tool_diffs,
        "historical_comparison_ranges": {"base": bw_range(base_gs), "scaled": bw_range(sc_gs)},
        "observable_collision_classes": classify_observable_collisions(scaled_bundle),
    }


def validate_scaled_bundle(
    base_bundle: Path,
    scaled_bundle: Path,
    strict_matcher: bool = False,
    check_rendered_files: bool = True,
) -> dict[str, Any]:
    cat_a = check_structural_and_ledger_invariants(base_bundle, scaled_bundle, check_rendered_files=check_rendered_files)
    try:
        cat_b = check_matcher_invariance(base_bundle, scaled_bundle)
        cat_b_clean = cat_b["false_open_historical_count"] == 0 and len(cat_b["tool_diffs_vs_base"]) == 0
    except Exception as exc:
        cat_b = {
            "error": str(exc),
            "false_open_historical_count": None,
            "false_open_by_vendor": {},
            "false_open_sample": [],
            "tool_diffs_vs_base": {},
        }
        cat_b_clean = False
    return {
        "base_bundle": str(base_bundle),
        "scaled_bundle": str(scaled_bundle),
        "scale_generator_sha256": _sha256(DATA_GEN / "scale_bundle.py"),
        "category_a": cat_a,
        "category_b": cat_b,
        "category_a_passed": len(cat_a["errors"]) == 0,
        "category_b_clean": cat_b_clean,
        "strict_matcher": strict_matcher,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_bundle", type=Path)
    ap.add_argument("scaled_bundle", type=Path)
    ap.add_argument("--strict-matcher", action="store_true", help="also fail on Category B matcher differences")
    ap.add_argument("--json-out", type=Path)
    a = ap.parse_args(argv)

    rep = validate_scaled_bundle(a.base_bundle, a.scaled_bundle, strict_matcher=a.strict_matcher)
    if a.json_out:
        a.json_out.parent.mkdir(parents=True, exist_ok=True)
        a.json_out.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")

    ca, cb = rep["category_a"], rep["category_b"]
    print(f"Bundle: {a.scaled_bundle} counts={ca['counts']}")
    if ca["errors"]:
        print(f"Category A FAILED ({len(ca['errors'])} errors):")
        for e in ca["errors"]:
            print(f"  - {e}")
    else:
        print("Category A (ledger/IDs/filenames/gold-invariance): PASS")
    if rep["category_b_clean"]:
        print("Category B (deterministic link_payments matcher invariance): CLEAN (0 diffs)")
    else:
        obs = cb.get("observable_collision_classes") or {}
        print(
            f"Category B LIMITATION: {cb['false_open_historical_count']} historical paid bills left open "
            f"({cb['false_open_by_vendor']}); observable=[local={len(obs.get('unique_local', []))}, "
            f"joint={len(obs.get('unique_joint', []))}, non_id={len(obs.get('not_identifiable', []))}]; "
            f"{len(cb['tool_diffs_vs_base'])} tool snapshots differ: {sorted(cb['tool_diffs_vs_base'])}"
        )
    if cb.get("historical_comparison_ranges"):
        print(f"Historical BeanWorks prior range: {cb['historical_comparison_ranges']}")

    if not rep["category_a_passed"]:
        return 1
    if a.strict_matcher and not rep["category_b_clean"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
