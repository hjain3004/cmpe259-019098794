"""Verify challenge YAML and challenge gold YAML directly against a bundle's ledger.json.

    cd project
    python evaluation/challenge/check_challenge_gold.py data/dev/cafe_01 evaluation/challenge/cafe_challenge.yaml evaluation/challenge/cafe_challenge_gold.yaml
    python evaluation/challenge/check_challenge_gold.py data/dev/plumbing_01 evaluation/challenge/plumbing_challenge.yaml evaluation/challenge/plumbing_challenge_gold.yaml
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import yaml

ZERO = Decimal("0.00")


def _m(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


def _due(inv: dict) -> date:
    if inv.get("stated_due_date"):
        return date.fromisoformat(inv["stated_due_date"])
    days = int(re.search(r"\d+", inv["payment_terms"]).group())
    return date.fromisoformat(inv["issue_date"]) + timedelta(days=days)


def check_challenge(bundle: Path, challenge_yaml: Path, gold_yaml: Path) -> list[str]:
    ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
    chal = yaml.safe_load(challenge_yaml.read_text(encoding="utf-8"))
    gold = yaml.safe_load(gold_yaml.read_text(encoding="utf-8"))

    clock = date.fromisoformat(ledger["business"]["evaluation_clock"])
    invoices = {i["invoice_number"]: i for i in ledger["invoices"]}
    credits = ledger.get("credits", [])
    payments = ledger.get("payments", [])
    bank = {t["txn_id"]: t for t in ledger["bank"]}
    vendors = {v["vendor_id"]: v for v in ledger["vendors"]}
    messages = {m["msg_id"]: m for m in ledger.get("messages", [])}

    valid_docs = (
        {f"inv_{n}" for n in invoices}
        | {f"cn_{c['credit_id']}" for c in credits}
        | set(bank.keys())
        | {f"vh_{vid}" for vid in vendors}
        | {f"msg_{mid}" for mid in messages}
    )

    # Recompute ledger facts per invoice:
    paid_map: dict[str, Decimal] = {}
    for p in payments:
        if date.fromisoformat(bank[p["txn_id"]]["posted_on"]) <= clock:
            paid_map[p["invoice_number"]] = paid_map.get(p["invoice_number"], ZERO) + _m(p["amount_applied"])

    cred_map: dict[str, Decimal] = {}
    for c in credits:
        if date.fromisoformat(c["issued_on"]) <= clock:
            cred_map[c["invoice_number"]] = cred_map.get(c["invoice_number"], ZERO) + _m(c["amount"])

    # Compute confirmed-only and ledger-truth remaining per non-duplicate invoice
    rem_ledger: dict[str, Decimal] = {}
    rem_confirmed: dict[str, Decimal] = {}
    for num, inv in invoices.items():
        tot = _m(inv["total"])
        c_amt = cred_map.get(num, ZERO)
        p_amt = paid_map.get(num, ZERO)
        rem_ledger[num] = max(tot - c_amt - p_amt, ZERO)
        # Confirmed if txn descriptor mentions invoice_number OR exact full-bill payment
        conf_amt = ZERO
        for p in payments:
            if p["invoice_number"] != num:
                continue
            tx = bank[p["txn_id"]]
            if num.upper() in tx["descriptor"].upper() or _m(p["amount_applied"]) == tot - c_amt:
                conf_amt += _m(p["amount_applied"])
        rem_confirmed[num] = max(tot - c_amt - conf_amt, ZERO)

    # Valid numerical/string tokens derived from the ledger
    valid_amounts: set[str] = set()
    valid_dates: set[str] = set()
    valid_last4: set[str] = set()
    valid_contacts: set[str] = set()

    for num, inv in invoices.items():
        valid_amounts.add(f"{_m(inv['total']):.2f}")
        valid_amounts.add(f"{_m(inv['total']):.2f} {inv['currency']}")
        valid_amounts.add(f"{rem_ledger[num]:.2f}")
        valid_amounts.add(f"{rem_ledger[num]:.2f} {inv['currency']}")
        valid_amounts.add(f"{rem_confirmed[num]:.2f}")
        valid_amounts.add(f"{rem_confirmed[num]:.2f} {inv['currency']}")
        valid_dates.add(inv["issue_date"])
        valid_dates.add(_due(inv).isoformat())
        valid_last4.add(inv["remit"]["account_number"][-4:])
    for tx in bank.values():
        amt = abs(_m(tx["amount"]))
        valid_amounts.add(f"{amt:.2f}")
        valid_amounts.add(f"{amt:.2f} {tx['currency']}")
        valid_dates.add(tx["posted_on"])
    for v in vendors.values():
        valid_last4.add(v["verified_payment"]["account_number"][-4:])
        valid_contacts.add(v["trusted_contact"].split(",")[0].strip())

    # Derived vendor open totals (excluding duplicate_of), hypothetical nets, and due-by-Oct-2 sums
    non_dup_invs = [n for n, inv in invoices.items() if not inv.get("duplicate_of")]
    for vid in vendors:
        v_invs = [n for n in non_dup_invs if invoices[n]["vendor_id"] == vid]
        sum_ledg = sum((rem_ledger[n] for n in v_invs if rem_ledger[n] > ZERO), ZERO)
        sum_conf = sum((rem_confirmed[n] for n in v_invs if rem_confirmed[n] > ZERO), ZERO)
        valid_amounts.update({f"{sum_ledg:.2f}", f"{sum_ledg:.2f} USD", f"{sum_conf:.2f}", f"{sum_conf:.2f} USD"})
        # Subtract any duplicate payment amount on this vendor
        dup_pmts = [
            _m(p["amount_applied"])
            for n in v_invs
            if paid_map.get(n, ZERO) > _m(invoices[n]["total"])
            for p in payments if p["invoice_number"] == n
        ]
        for dp in set(dup_pmts):
            for base in (sum_ledg, sum_conf):
                net = base - dp
                valid_amounts.update({f"{net:.2f}", f"{net:.2f} USD"})

    # Budget sums (pairs of clean open bills due <= 2026-10-02)
    oct2 = date(2026, 10, 2)
    clean_due = [
        n for n in non_dup_invs
        if rem_ledger[n] > ZERO and _due(invoices[n]) <= oct2
    ]
    for i, a in enumerate(clean_due):
        for b in clean_due[i + 1 :]:
            s = rem_ledger[a] + rem_ledger[b]
            valid_amounts.update({f"{s:.2f}", f"{s:.2f} USD"})

    errors: list[str] = []
    if gold.get("scenario") != ledger["business"]["business_id"]:
        errors.append(f"scenario mismatch: {gold.get('scenario')} != {ledger['business']['business_id']}")

    convs = {c["id"]: c for c in chal.get("conversations", [])}
    if set(convs.keys()) != {f"CH{i}" for i in range(1, 8)}:
        errors.append(f"expected CH1..CH7 in {challenge_yaml.name}, got {sorted(convs)}")

    for cid, conv in convs.items():
        if cid not in gold:
            errors.append(f"{cid}: missing from {gold_yaml.name}")
            continue
        g_entry = gold[cid]
        g_turns = g_entry["turns"] if isinstance(g_entry, dict) else g_entry
        if len(g_turns) != len(conv["turns"]):
            errors.append(f"{cid}: turn count {len(g_turns)} != {len(conv['turns'])}")
            continue
        for ti, gt in enumerate(g_turns):
            for ev in gt.get("evidence", []):
                if ev not in valid_docs:
                    errors.append(f"{cid}[{ti}]: unknown evidence {ev!r}")
            for val in gt.get("values", []):
                choices = val if isinstance(val, list) else [val]
                for ch in choices:
                    s = str(ch)
                    if s in invoices or s in bank or s in messages or s in valid_last4 or s in valid_contacts:
                        continue
                    if s in ("paid", "overpaid", "unpaid", "partial", "paid in full"):
                        continue
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
                        if s not in valid_dates:
                            errors.append(f"{cid}[{ti}]: date {s!r} not in derived ledger dates")
                        continue
                    if re.match(r"^\d+\.\d{2}(?:\s+[A-Z]{3})?$", s):
                        if s not in valid_amounts:
                            errors.append(f"{cid}[{ti}]: amount {s!r} not in derived ledger amounts")
                        continue
                    errors.append(f"{cid}[{ti}]: unrecognized value {s!r} not grounded in ledger")
            bc = gt.get("budget_check")
            if bc:
                for b in bc.get("overdue_clean", []):
                    if b not in invoices or rem_ledger[b] <= ZERO:
                        errors.append(f"{cid}[{ti}]: overdue_clean {b!r} is not an open invoice")
                for b, info in bc.get("uncertain_bills", {}).items():
                    if b not in invoices:
                        errors.append(f"{cid}[{ti}]: uncertain_bills {b!r} is not an invoice")
                        continue
                    ca = str(info.get("certain_amount", ""))
                    if ca != "0.00" and ca not in valid_amounts:
                        errors.append(f"{cid}[{ti}]: uncertain_bills {b!r} certain_amount {ca!r} not in ledger amounts")
    return errors


def main(argv: list[str] | None = None) -> int:
    if len(argv or sys.argv[1:]) != 3:
        print(__doc__)
        return 2
    b, c, g = [Path(x) for x in (argv or sys.argv[1:])]
    errs = check_challenge(b, c, g)
    if errs:
        for e in errs:
            print("FAIL:", e)
        return 1
    print(f"OK: {c.name} and {g.name} verified against {b}/ledger.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
