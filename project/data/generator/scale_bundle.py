"""Scale a synthetic bundle by adding look-alike historical documents.

    cd project
    python data/generator/scale_bundle.py data/dev/cafe_01 4 data/dev/cafe_01_x4
    python data/generator/scale_bundle.py data/dev/cafe_01 16 data/dev/cafe_01_x16
    python data/generator/scale_bundle.py data/dev/cafe_01 32 data/dev/cafe_01_ctrl_x32 --profile controlled

Profiles:
    ambiguity   (default) keeps plain vendor descriptors without invoice numbers,
                creating amount-matching ambiguity at x32/x64 alongside corpus growth.
    controlled  appends the paid invoice number to added background payment
                descriptors so historical settlements are observable, isolating corpus volume.

Every added invoice is issued and fully paid before 2026-07-01, with a matching
bank row and a linked payment in ledger.json.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import shutil
import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
RENDER_PY = PROJECT / "data" / "generator" / "render.py"
PROFILES = ("ambiguity", "controlled")

FORBIDDEN_AMOUNTS = {
    Decimal("615.40"), Decimal("842.00"), Decimal("1118.25"), Decimal("389.60"),
    Decimal("268.90"), Decimal("512.30"), Decimal("486.00"), Decimal("1962.00"),
    Decimal("300.00"), Decimal("1750.00"),
}

_VENDOR_CONFIG = {
    "v_northside": {
        "prefix": "NS",
        "start_num": 800,
        "terms": "Net 30",
        "print_due": True,
        "tax_rate": Decimal("0.0825"),
        "descriptor": "NORTHSIDE SUP CO 8841",
        "items": [
            ("Paper cups 12 oz, sleeve of 50", "sleeve", Decimal("14.50")),
            ("Compostable lids 12 oz, sleeve of 50", "sleeve", Decimal("9.75")),
            ("Paper cups 16 oz, sleeve of 50", "sleeve", Decimal("16.90")),
            ("Napkins, case", "case", Decimal("24.00")),
            ("Sanitizer, gallon", "gallon", Decimal("38.50")),
        ],
    },
    "v_greenway": {
        "prefix": "GP",
        "start_num": 100,
        "terms": "Net 15",
        "print_due": False,
        "tax_rate": Decimal("0.00"),
        "descriptor": "GREENWAY PRODUCE ACH",
        "items": [
            ("Strawberries, flat", "flat", Decimal("24.50")),
            ("Bananas, case", "case", Decimal("28.90")),
            ("Avocados, case", "case", Decimal("52.40")),
            ("Spinach, case", "case", Decimal("31.25")),
            ("Lemons, case", "case", Decimal("35.20")),
        ],
    },
    "v_beanworks": {
        "prefix": "BW",
        "start_num": 500,
        "terms": "Net 30",
        "print_due": True,
        "tax_rate": Decimal("0.00"),
        "descriptor": "BEANWORKS COFFEE",
        "items": [
            ("Espresso Blend, 5 lb bag", "bag", Decimal("34.50")),
            ("Decaf House Blend, 2 lb bag", "bag", Decimal("18.00")),
            ("Single Origin Ethiopia, 2 lb bag", "bag", Decimal("18.00")),
        ],
    },
}

_UNRELATED_BANK = [
    ("DEPOSIT SQUARE INC", Decimal("1420.00"), Decimal("2390.00"), True),
    ("PG&E UTILITY", Decimal("185.00"), Decimal("245.00"), False),
    ("COMCAST BUSINESS", Decimal("94.50"), Decimal("98.50"), False),
    ("SHELL OIL 5741", Decimal("48.00"), Decimal("72.00"), False),
    ("COSTCO WHSE #0144", Decimal("55.00"), Decimal("135.00"), False),
    ("ADOBE *CREATIVE CLD", Decimal("129.99"), Decimal("129.99"), False),
]


def _next_txn_id(existing: set[str], counter: list[int]) -> str:
    while True:
        tid = f"txn_{counter[0]:04d}"
        counter[0] += 1
        if tid not in existing:
            existing.add(tid)
            return tid


def _next_invoice_number(prefix: str, existing: set[str], seq: dict[str, int], vid: str) -> str:
    while True:
        num = f"{prefix}-{seq[vid]}"
        seq[vid] += 1
        if num not in existing:
            existing.add(num)
            return num


def _next_msg_id(existing: set[str], counter: list[int]) -> str:
    while True:
        mid = f"m{counter[0]:03d}"
        counter[0] += 1
        if mid not in existing:
            existing.add(mid)
            return mid


def _next_po_ref(existing: set[str], counter: list[int]) -> str:
    while True:
        ref = f"PO-{counter[0]}"
        if ref not in existing:
            existing.add(ref)
            return ref
        counter[0] += 1


def scale_ledger(base_ledger: dict, factor: int, seed: int = 259, profile: str = "ambiguity") -> dict:
    """Return a scaled copy of base_ledger with ~factor x as many documents."""
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}, got {profile!r}")
    if factor < 1:
        raise ValueError("factor must be >= 1")
    led = copy.deepcopy(base_ledger)
    if factor == 1:
        return led

    rng = random.Random(seed)
    vendors = {v["vendor_id"]: v for v in led["vendors"]}
    existing_invoices = {i["invoice_number"] for i in led["invoices"]}
    existing_txns = {t["txn_id"] for t in led["bank"]}
    existing_msgs = {m["msg_id"] for m in led.get("messages", [])}
    existing_refs = {i["reference_or_po"] for i in led["invoices"] if i.get("reference_or_po")}

    txn_counter = [1000]
    vendor_ids = [v["vendor_id"] for v in led["vendors"]]
    for vid in vendor_ids:
        if vid not in _VENDOR_CONFIG:
            raise ValueError(f"unsupported vendor {vid!r} for scale_ledger")

    # Track next invoice number per vendor, skipping any reserved existing numbers.
    inv_seq = {vid: _VENDOR_CONFIG[vid]["start_num"] for vid in vendor_ids}
    po_counter = [1000]
    msg_counter = [len(led.get("messages", [])) + 1]

    n_extra_inv = (factor - 1) * len(led["invoices"])
    n_extra_msg = (factor - 1) * len(led.get("messages", []))
    n_extra_unlinked_bank = (factor - 1) * max(1, len(led["bank"]) - len(led.get("payments", [])))

    # Spread historical dates across 2025-07-01 .. 2026-06-15 so everything is < 2026-07-01.
    start_day = date(2025, 7, 1)
    span_days = (date(2026, 6, 15) - start_day).days

    added_invoices: list[dict] = []
    for idx in range(n_extra_inv):
        vid = vendor_ids[idx % len(vendor_ids)]
        v = vendors[vid]
        vc = _VENDOR_CONFIG[vid]
        num = _next_invoice_number(vc["prefix"], existing_invoices, inv_seq, vid)
        po_counter[0] += 1
        po_ref = _next_po_ref(existing_refs, po_counter) if vid == "v_northside" else None

        issue_dt = start_day + timedelta(days=(idx * span_days) // max(1, n_extra_inv))
        paid_dt = issue_dt + timedelta(days=rng.randint(3, 12))
        if paid_dt >= date(2026, 7, 1):
            paid_dt = date(2026, 6, 28)

        chosen = rng.sample(vc["items"], k=min(2, len(vc["items"])))
        lines = []
        sub = Decimal("0.00")
        for desc, unit, price in chosen:
            qty = rng.randint(2, 10)
            lt = (Decimal(qty) * price).quantize(Decimal("0.01"))
            lines.append({
                "description": desc,
                "quantity": str(qty),
                "unit": unit,
                "unit_price": f"{price:.2f}",
                "line_total": f"{lt:.2f}",
            })
            sub += lt
        tax = (sub * vc["tax_rate"]).quantize(Decimal("0.01"))
        total = sub + tax
        # Ensure we never collide with a forbidden gold amount
        attempts = 0
        while total in FORBIDDEN_AMOUNTS:
            attempts += 1
            if attempts > 50:
                raise RuntimeError(f"could not avoid FORBIDDEN_AMOUNTS for {num}")
            lines[0]["quantity"] = str(int(lines[0]["quantity"]) + 1)
            lt0 = (Decimal(lines[0]["quantity"]) * Decimal(lines[0]["unit_price"])).quantize(Decimal("0.01"))
            lines[0]["line_total"] = f"{lt0:.2f}"
            sub = sum(Decimal(l["line_total"]) for l in lines)
            tax = (sub * vc["tax_rate"]).quantize(Decimal("0.01"))
            total = sub + tax

        vp = v["verified_payment"]
        inv_obj = {
            "invoice_number": num,
            "vendor_id": vid,
            "printed_vendor_name": v["canonical_name"],
            "issue_date": issue_dt.isoformat(),
            "payment_terms": vc["terms"],
            "print_due_date": vc["print_due"],
            "stated_due_date": None,
            "currency": "USD",
            "lines": lines,
            "subtotal": f"{sub:.2f}",
            "tax": f"{tax:.2f}",
            "total": f"{total:.2f}",
            "remit": {
                "bank_name": vp["bank_name"],
                "account_number": vp["account_number"],
                "routing_number": vp["routing_number"],
            },
            "reference_or_po": po_ref,
            "memo": None,
            "attack": None,
        }
        led["invoices"].append(inv_obj)
        added_invoices.append(inv_obj)

        tid = _next_txn_id(existing_txns, txn_counter)
        desc = f"{vc['descriptor']} {num}" if profile == "controlled" else vc["descriptor"]
        led["bank"].append({
            "txn_id": tid,
            "posted_on": paid_dt.isoformat(),
            "amount": f"-{total:.2f}",
            "currency": "USD",
            "descriptor": desc,
        })
        led["payments"].append({
            "txn_id": tid,
            "invoice_number": num,
            "amount_applied": f"{total:.2f}",
        })

    # Routine vendor messages (order confirmations / delivery notes, < 2026-07-01)
    for j in range(n_extra_msg):
        inv_ref = added_invoices[j % len(added_invoices)]
        v = vendors[inv_ref["vendor_id"]]
        mid = _next_msg_id(existing_msgs, msg_counter)
        m_date = date.fromisoformat(inv_ref["issue_date"]) + timedelta(days=1)
        led["messages"].append({
            "msg_id": mid,
            "received_on": m_date.isoformat(),
            "channel": "email",
            "from": f"{v['canonical_name']} <orders@example.com>",
            "subject": f"Order confirmation for {inv_ref['invoice_number']}",
            "body": (
                f"Hello,\n\nYour delivery for {inv_ref['invoice_number']} was completed on "
                f"{inv_ref['issue_date']}. Thank you for your business!\n\n{v['canonical_name']}"
            ),
            "kind": "other",
            "invoice_refs": [inv_ref["invoice_number"]],
        })

    # Unrelated historical bank rows (< 2026-07-01)
    for k in range(n_extra_unlinked_bank):
        desc, lo, hi, is_pos = _UNRELATED_BANK[k % len(_UNRELATED_BANK)]
        cents = rng.randint(int(lo * 100), int(hi * 100))
        amt = (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))
        attempts = 0
        while amt in FORBIDDEN_AMOUNTS:
            attempts += 1
            if attempts > 50:
                raise RuntimeError(f"could not avoid FORBIDDEN_AMOUNTS for unlinked bank row {k}")
            amt += Decimal("1.11")
        signed = amt if is_pos else -amt
        b_date = start_day + timedelta(days=(k * span_days) // max(1, n_extra_unlinked_bank))
        tid = _next_txn_id(existing_txns, txn_counter)
        led["bank"].append({
            "txn_id": tid,
            "posted_on": b_date.isoformat(),
            "amount": f"{signed:.2f}",
            "currency": "USD",
            "descriptor": desc,
        })

    led["invoices"].sort(key=lambda x: (x["issue_date"], x["invoice_number"]))
    led["bank"].sort(key=lambda x: (x["posted_on"], x["txn_id"]))
    led["messages"].sort(key=lambda x: (x["received_on"], x["msg_id"]))
    return led


def build_scaled_bundle(
    source_bundle: Path,
    factor: int,
    out_bundle: Path,
    seed: int = 259,
    profile: str = "ambiguity",
) -> None:
    base = json.loads((source_bundle / "ledger.json").read_text(encoding="utf-8"))
    scaled = scale_ledger(base, factor=factor, seed=seed, profile=profile)
    out_bundle.mkdir(parents=True, exist_ok=True)
    (out_bundle / "ledger.json").write_text(json.dumps(scaled, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(source_bundle / "gold.yaml", out_bundle / "gold.yaml")
    subprocess.run([sys.executable, str(RENDER_PY), str(out_bundle)], check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_bundle", type=Path)
    ap.add_argument("factor", type=int)
    ap.add_argument("out_bundle", type=Path)
    ap.add_argument("--seed", type=int, default=259)
    ap.add_argument("--profile", choices=PROFILES, default="ambiguity")
    a = ap.parse_args(argv)

    build_scaled_bundle(a.source_bundle, a.factor, a.out_bundle, seed=a.seed, profile=a.profile)
    print(f"wrote and rendered {a.out_bundle} (profile={a.profile})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
