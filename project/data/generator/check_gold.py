"""Recompute every money, date, status and fact value in a bundle's gold.yaml
directly from its ledger.json using plain Python and Decimal arithmetic.

Independent of cashbooks.tools: does not import any cashbooks package module.
Exits non-zero on any mismatch.

    python data/generator/check_gold.py data/dev/cafe_01
    python data/generator/check_gold.py data/dev/plumbing_01
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


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _m(s: str | int | float | Decimal) -> Decimal:
    return Decimal(str(s)).quantize(Decimal("0.01"))


def _fmt_money(amount: Decimal, currency: str = "USD") -> str:
    return f"{amount:.2f} {currency}"


def _fmt_plain(amount: Decimal) -> str:
    return f"{amount:.2f}"


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


def _effective_due(inv: dict) -> date:
    return _stated_due(inv) or _derived_due(inv)


class LedgerModel:
    """Pure-Python ledger model for independent verification of gold.yaml."""

    def __init__(self, bundle: Path):
        self.bundle = bundle
        self.ledger = json.loads((bundle / "ledger.json").read_text(encoding="utf-8"))
        self.clock = date.fromisoformat(self.ledger["business"]["evaluation_clock"])
        self.vendors = {v["vendor_id"]: v for v in self.ledger["vendors"]}
        self.invoices = {i["invoice_number"]: i for i in self.ledger["invoices"]}
        self.credits = self.ledger.get("credits", [])
        self.bank = {t["txn_id"]: t for t in self.ledger["bank"]}
        self.payments = self.ledger.get("payments", [])
        self.all_paid = self._compute_paid_map()

    def _compute_paid_map(self) -> dict[str, Decimal]:
        """Return ledger-truth amount paid per invoice as of evaluation clock."""
        all_paid: dict[str, Decimal] = {}
        for p in self.payments:
            num = p["invoice_number"]
            amt = _m(p["amount_applied"])
            txn = self.bank[p["txn_id"]]
            posted = date.fromisoformat(txn["posted_on"])
            if posted > self.clock:
                continue
            all_paid[num] = all_paid.get(num, ZERO) + amt
        return all_paid

    def credited_as_of(self, num: str, as_of: date | None = None) -> Decimal:
        cutoff = as_of or self.clock
        return sum(
            (_m(c["amount"]) for c in self.credits if c["invoice_number"] == num and date.fromisoformat(c["issued_on"]) <= cutoff),
            ZERO,
        )

    def remaining_ledger(self, num: str) -> Decimal:
        inv = self.invoices[num]
        rem = _m(inv["total"]) - self.credited_as_of(num) - self.all_paid.get(num, ZERO)
        return max(rem, ZERO)

    def status_ledger(self, num: str) -> str:
        inv = self.invoices[num]
        settled = self.credited_as_of(num) + self.all_paid.get(num, ZERO)
        total = _m(inv["total"])
        if settled == ZERO:
            return "unpaid"
        if settled < total:
            return "partial"
        if settled == total:
            return "paid"
        return "overpaid"

    def is_overdue(self, num: str, as_of: date | None = None) -> bool:
        cutoff = as_of or self.clock
        st = self.status_ledger(num)
        due = _effective_due(self.invoices[num])
        return st in ("unpaid", "partial") and due < cutoff

    def non_duplicate_invoices(self, nums: list[str] | None = None) -> list[str]:
        """Filter invoice numbers so any bill marked `duplicate_of` is counted only once."""
        candidates = nums if nums is not None else list(self.invoices.keys())
        return [num for num in candidates if not self.invoices[num].get("duplicate_of")]


def _extract_turns(entry: list | dict) -> list[dict]:
    if isinstance(entry, dict):
        return list(entry.get("turns", []))
    return list(entry)


def check_bundle(bundle: Path) -> list[str]:
    m = LedgerModel(bundle)
    gold = yaml.safe_load((bundle / "gold.yaml").read_text(encoding="utf-8"))
    errors: list[str] = []

    def fail(qid: str, msg: str) -> None:
        errors.append(f"{bundle.name} {qid}: {msg}")

    # Valid evidence prefixes from the ledger
    valid_docs = (
        {f"inv_{num}" for num in m.invoices}
        | {f"cn_{c['credit_id']}" for c in m.credits}
        | set(m.bank.keys())
        | {f"vh_{vid}" for vid in m.vendors}
        | {f"msg_{msg['msg_id']}" for msg in m.ledger.get("messages", [])}
    )

    for qid, raw_entry in gold.items():
        if not re.fullmatch(r"Q\d{2}", str(qid)):
            continue
        turns = _extract_turns(raw_entry)
        for ti, turn in enumerate(turns):
            vals = turn.get("values") or {}
            ev = turn.get("evidence") or []
            for e in ev:
                if e not in valid_docs:
                    fail(f"{qid}[{ti}]", f"evidence {e!r} does not exist in ledger")

            # Verify every value in gold.yaml against ledger arithmetic
            for k, v in vals.items():
                vs = str(v)

                # Invoice number references
                if k in ("bill", "first", "second", "third", "fourth"):
                    if vs not in m.invoices:
                        fail(f"{qid}[{ti}]", f"{k}={vs!r} is not a valid invoice_number in ledger")

                # Status values
                elif k == "status":
                    bill_num = vals.get("bill")
                    if bill_num:
                        expected_st = m.status_ledger(bill_num)
                        if vs.lower() != expected_st:
                            fail(f"{qid}[{ti}]", f"status for {bill_num} is {vs!r}, ledger gives {expected_st!r}")
                    else:
                        # Q04 single-turn paid check: find the invoice referenced in evidence
                        inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                        txn_evs = [e for e in ev if e.startswith("txn_")]
                        if inv_evs:
                            bnum = inv_evs[0]
                            expected_st = m.status_ledger(bnum)
                            if vs.lower() != expected_st:
                                fail(f"{qid}[{ti}]", f"status for {bnum} is {vs!r}, ledger gives {expected_st!r}")
                        elif txn_evs:
                            pmts = [p for p in m.payments if p["txn_id"] == txn_evs[0]]
                            if not pmts or vs.lower() != m.status_ledger(pmts[0]["invoice_number"]):
                                fail(f"{qid}[{ti}]", f"status for txn {txn_evs[0]} mismatch: {vs!r}")

                # Remaining balance on a specific bill (Q01, Q06, Q25)
                elif k in ("balance", "remaining"):
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = vals.get("bill") or (inv_evs[0] if inv_evs else None)
                    if not bnum or bnum not in m.invoices:
                        fail(f"{qid}[{ti}]", f"cannot determine invoice for {k}={vs!r}")
                    else:
                        cur = m.invoices[bnum]["currency"]
                        expected_rem = _fmt_money(m.remaining_ledger(bnum), cur)
                        if vs != expected_rem:
                            fail(f"{qid}[{ti}]", f"{k} for {bnum} is {vs!r}, ledger gives {expected_rem!r}")

                # Dates: due, issue, date, stated, derived
                elif k == "due":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = vals.get("bill") or (inv_evs[0] if inv_evs else None)
                    if bnum and bnum in m.invoices:
                        due_set = {_effective_due(m.invoices[bnum]).isoformat()}
                        if vals.get("second") and vals["second"] in m.invoices:
                            due_set.add(_effective_due(m.invoices[vals["second"]]).isoformat())
                        if vs not in due_set:
                            fail(f"{qid}[{ti}]", f"due for {bnum} is {vs!r}, ledger gives {due_set}")
                elif k == "issue":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = vals.get("bill") or (inv_evs[0] if inv_evs else None)
                    if bnum and m.invoices[bnum]["issue_date"] != vs:
                        fail(f"{qid}[{ti}]", f"issue date for {bnum} is {vs!r}, ledger has {m.invoices[bnum]['issue_date']!r}")
                elif k == "stated":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = inv_evs[0]
                    st = _stated_due(m.invoices[bnum])
                    if not st or st.isoformat() != vs:
                        fail(f"{qid}[{ti}]", f"stated due date for {bnum} is {vs!r}, ledger has {st}")
                elif k == "derived":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = inv_evs[0]
                    der = _derived_due(m.invoices[bnum])
                    if der.isoformat() != vs:
                        fail(f"{qid}[{ti}]", f"derived due date for {bnum} is {vs!r}, ledger has {der.isoformat()}")
                elif k == "date":
                    txn_evs = [e for e in ev if e.startswith("txn_")]
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    if txn_evs:
                        posted = m.bank[txn_evs[0]]["posted_on"]
                        if posted != vs:
                            fail(f"{qid}[{ti}]", f"txn date is {vs!r}, ledger has {posted!r}")
                    elif inv_evs:
                        iss = m.invoices[inv_evs[0]]["issue_date"]
                        if iss != vs:
                            fail(f"{qid}[{ti}]", f"invoice issue date is {vs!r}, ledger has {iss!r}")

                # Subtotal, tax, line_sum, stated_total, difference (Q08, Q24)
                elif k in ("subtotal", "tax"):
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = inv_evs[0]
                    got = _fmt_plain(_m(m.invoices[bnum][k]))
                    if vs != got:
                        fail(f"{qid}[{ti}]", f"{k} for {bnum} is {vs!r}, ledger has {got!r}")
                elif k == "line_sum":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = inv_evs[0]
                    inv = m.invoices[bnum]
                    lsum = sum((_m(ln["line_total"]) for ln in inv["lines"]), ZERO)
                    if vs != _fmt_money(lsum, inv["currency"]):
                        fail(f"{qid}[{ti}]", f"line_sum for {bnum} is {vs!r}, ledger has {_fmt_money(lsum, inv['currency'])!r}")
                elif k == "stated_total":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = inv_evs[0]
                    inv = m.invoices[bnum]
                    if vs != _fmt_money(_m(inv["total"]), inv["currency"]):
                        fail(f"{qid}[{ti}]", f"stated_total for {bnum} is {vs!r}, ledger has {_fmt_money(_m(inv['total']), inv['currency'])!r}")
                elif k == "difference":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    bnum = inv_evs[0]
                    inv = m.invoices[bnum]
                    lsum = sum((_m(ln["line_total"]) for ln in inv["lines"]), ZERO)
                    diff = abs(_m(inv["total"]) - lsum)
                    if vs != _fmt_plain(diff):
                        fail(f"{qid}[{ti}]", f"difference for {bnum} is {vs!r}, ledger has {_fmt_plain(diff)!r}")

                # Totals (Q02, Q08, Q19, Q25, Q28)
                elif k == "total":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    if len(inv_evs) == 1:
                        bnum = inv_evs[0]
                        inv = m.invoices[bnum]
                        allowed = {_fmt_money(_m(inv["total"]), inv["currency"]), _fmt_plain(_m(inv["total"]))}
                        if vs not in allowed:
                            fail(f"{qid}[{ti}]", f"total for {bnum} is {vs!r}, ledger has {allowed}")
                    else:
                        cur = m.invoices[inv_evs[0]]["currency"]
                        unique_invs = m.non_duplicate_invoices(inv_evs)
                        sum_ledg = sum((m.remaining_ledger(b) for b in unique_invs), ZERO)
                        expected_tot = _fmt_money(sum_ledg, cur)
                        if vs != expected_tot:
                            fail(f"{qid}[{ti}]", f"sum total for {unique_invs} is {vs!r}, ledger gives {expected_tot!r}")
                elif k == "overdue_total":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    cur = m.invoices[inv_evs[0]]["currency"]
                    if not all(m.is_overdue(b) for b in inv_evs):
                        fail(f"{qid}[{ti}]", f"not all bills in {inv_evs} are overdue at {m.clock}")
                    unique_invs = m.non_duplicate_invoices(inv_evs)
                    sum_ledg = sum((m.remaining_ledger(b) for b in unique_invs), ZERO)
                    if vs != _fmt_money(sum_ledg, cur):
                        fail(f"{qid}[{ti}]", f"overdue_total is {vs!r}, ledger gives {_fmt_money(sum_ledg, cur)!r}")
                elif k in ("usd_total", "eur_total"):
                    target_cur = "USD" if k == "usd_total" else "EUR"
                    open_invs = m.non_duplicate_invoices(
                        [num for num, inv in m.invoices.items() if inv["currency"] == target_cur]
                    )
                    sum_ledg = sum((m.remaining_ledger(b) for b in open_invs), ZERO)
                    expected_tot = _fmt_money(sum_ledg, target_cur)
                    if vs != expected_tot:
                        fail(f"{qid}[{ti}]", f"{k} is {vs!r}, ledger gives {expected_tot!r}")

                # Payment, credit, amount (Q17, Q25, Q26, Q30)
                elif k == "payment":
                    txn_evs = [e for e in ev if e.startswith("txn_")]
                    b_amt = abs(_m(m.bank[txn_evs[0]]["amount"]))
                    if vs != _fmt_plain(b_amt):
                        fail(f"{qid}[{ti}]", f"payment is {vs!r}, bank has {_fmt_plain(b_amt)!r}")
                elif k == "credit":
                    cn_evs = [e[3:] for e in ev if e.startswith("cn_")]
                    cr = next(c for c in m.credits if c["credit_id"] == cn_evs[0])
                    if vs != _fmt_plain(_m(cr["amount"])):
                        fail(f"{qid}[{ti}]", f"credit is {vs!r}, ledger has {_fmt_plain(_m(cr['amount']))!r}")
                elif k == "amount":
                    txn_evs = [e for e in ev if e.startswith("txn_")]
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    if txn_evs:
                        tx = m.bank[txn_evs[0]]
                        got = _fmt_money(abs(_m(tx["amount"])), tx["currency"])
                        if vs != got:
                            fail(f"{qid}[{ti}]", f"txn amount is {vs!r}, ledger has {got!r}")
                    elif inv_evs:
                        inv = m.invoices[inv_evs[0]]
                        got = _fmt_money(_m(inv["total"]), inv["currency"])
                        if vs != got:
                            fail(f"{qid}[{ti}]", f"invoice amount is {vs!r}, ledger has {got!r}")

                # Remit last4 and totals comparison (Q12, Q13, Q18, Q22)
                elif k in ("new_last4", "last4"):
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    vh_evs = [e[3:] for e in ev if e.startswith("vh_")]
                    possible_last4 = set()
                    for b in inv_evs:
                        possible_last4.add(m.invoices[b]["remit"]["account_number"][-4:])
                    for v in vh_evs:
                        possible_last4.add(m.vendors[v]["verified_payment"]["account_number"][-4:])
                    if vs not in possible_last4:
                        fail(f"{qid}[{ti}]", f"{k}={vs!r} not in {possible_last4}")
                elif k == "old_last4":
                    vh_evs = [e[3:] for e in ev if e.startswith("vh_")]
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    possible_last4 = set()
                    for v in vh_evs:
                        possible_last4.add(m.vendors[v]["verified_payment"]["account_number"][-4:])
                    for b in inv_evs:
                        possible_last4.add(m.invoices[b]["remit"]["account_number"][-4:])
                    if vs not in possible_last4:
                        fail(f"{qid}[{ti}]", f"old_last4={vs!r} not in {possible_last4}")
                elif k in ("this_total", "new_total"):
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    inv = m.invoices[inv_evs[0]]
                    if vs != _fmt_money(_m(inv["total"]), inv["currency"]):
                        fail(f"{qid}[{ti}]", f"{k} is {vs!r}, ledger has {_fmt_money(_m(inv['total']), inv['currency'])!r}")
                elif k in ("previous_total", "old_total"):
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    inv = m.invoices[inv_evs[1]]
                    if vs != _fmt_plain(_m(inv["total"])):
                        fail(f"{qid}[{ti}]", f"{k} is {vs!r}, ledger has {_fmt_plain(_m(inv['total']))!r}")

                # Line-item purchases (Q14, Q15)
                elif k == "spend":
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    inv = m.invoices[inv_evs[0]]
                    # Either all lines on the August invoice or matching lines
                    all_sub = _m(inv["subtotal"])
                    copper_sub = sum((_m(ln["line_total"]) for ln in inv["lines"] if "copper" in ln["description"].lower() or "blend" in ln["description"].lower()), ZERO)
                    allowed = {_fmt_money(all_sub, inv["currency"]), _fmt_money(copper_sub, inv["currency"])}
                    if vs not in allowed:
                        fail(f"{qid}[{ti}]", f"spend is {vs!r}, ledger gives {allowed}")
                elif k in ("bags", "lengths"):
                    inv_evs = [e[4:] for e in ev if e.startswith("inv_")]
                    inv = m.invoices[inv_evs[0]]
                    qtys = {str(int(_m(ln["quantity"]))) for ln in inv["lines"]}
                    if vs not in qtys:
                        fail(f"{qid}[{ti}]", f"{k}={vs!r} not in invoice line quantities {qtys}")

                # Vendor contact / alias (Q11, Q20, Q22, Q27)
                elif k == "contact":
                    vh_evs = [e[3:] for e in ev if e.startswith("vh_")]
                    tc = m.vendors[vh_evs[0]]["trusted_contact"]
                    if vs.lower() not in tc.lower():
                        fail(f"{qid}[{ti}]", f"contact {vs!r} not in trusted_contact {tc!r}")
                elif k == "alias":
                    vh_evs = [e[3:] for e in ev if e.startswith("vh_")]
                    aliases = [a["alias"] for a in m.vendors[vh_evs[0]].get("aliases", []) if a.get("verified")]
                    if vs not in aliases:
                        fail(f"{qid}[{ti}]", f"alias {vs!r} not in verified aliases {aliases}")
                elif k == "answer":
                    vh_evs = [e[3:] for e in ev if e.startswith("vh_")]
                    aliases = [a["alias"] for a in m.vendors[vh_evs[0]].get("aliases", []) if a.get("verified")]
                    if (vs.lower() == "yes") != bool(aliases):
                        fail(f"{qid}[{ti}]", f"answer={vs!r} disagrees with verified aliases {aliases}")
                else:
                    fail(f"{qid}[{ti}]", f"unrecognized gold value key {k!r}")

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    all_errors: list[str] = []
    for arg in sys.argv[1:]:
        b = Path(arg)
        errs = check_bundle(b)
        if errs:
            all_errors.extend(errs)
            for e in errs:
                print(f"FAIL: {e}")
        else:
            gold = yaml.safe_load((b / "gold.yaml").read_text(encoding="utf-8"))
            q_count = sum(1 for k in gold if re.fullmatch(r"Q\d{2}", str(k)))
            print(f"OK: {b} ({q_count} conversations verified against ledger.json)")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
