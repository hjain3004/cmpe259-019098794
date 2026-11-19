"""Unit tests for data/generator/scale_bundle.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
CAFE = PROJECT / "data" / "dev" / "cafe_01"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_scale_ledger_preserves_gold_invariants():
    sb = _load_mod("scale_bundle", PROJECT / "data" / "generator" / "scale_bundle.py")
    base = json.loads((CAFE / "ledger.json").read_text(encoding="utf-8"))
    base_invs = {i["invoice_number"] for i in base["invoices"]}
    base_txns = {t["txn_id"] for t in base["bank"]}
    base_msgs = {m["msg_id"] for m in base["messages"]}

    s4 = sb.scale_ledger(base, factor=4, seed=259)
    assert len(s4["invoices"]) == 32
    assert len(s4["messages"]) == 16

    paid_by_inv = {}
    for p in s4["payments"]:
        paid_by_inv[p["invoice_number"]] = paid_by_inv.get(p["invoice_number"], Decimal("0")) + Decimal(p["amount_applied"])

    for inv in s4["invoices"]:
        if inv["invoice_number"] in base_invs:
            continue
        assert date.fromisoformat(inv["issue_date"]) < date(2026, 7, 1)
        assert Decimal(inv["total"]) not in sb.FORBIDDEN_AMOUNTS
        assert paid_by_inv.get(inv["invoice_number"]) == Decimal(inv["total"])

    for t in s4["bank"]:
        if t["txn_id"] in base_txns:
            continue
        assert date.fromisoformat(t["posted_on"]) < date(2026, 7, 1)
        assert abs(Decimal(t["amount"])) not in sb.FORBIDDEN_AMOUNTS

    for m in s4["messages"]:
        if m["msg_id"] in base_msgs:
            continue
        assert date.fromisoformat(m["received_on"]) < date(2026, 7, 1)
        assert m["kind"] == "other"


def test_scaled_bundles_pass_check_gold():
    cg = _load_mod("check_gold", PROJECT / "data" / "generator" / "check_gold.py")
    for name in ("cafe_01_x4", "cafe_01_x16"):
        bdir = PROJECT / "data" / "dev" / name
        if bdir.exists():
            errs = cg.check_bundle(bdir)
            assert errs == [], f"{name} check_gold errors: {errs}"
