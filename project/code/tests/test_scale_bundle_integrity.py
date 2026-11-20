"""Offline integrity tests for data/generator/scale_bundle.py and evaluation/validate_scaled_bundle.py."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
CAFE = PROJECT / "data" / "dev" / "cafe_01"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_uniqueness_at_x1_x4_x16_x32_x64_and_x4_x16_reproducibility():
    sb = _load_mod("scale_bundle", PROJECT / "data" / "generator" / "scale_bundle.py")
    base = json.loads((CAFE / "ledger.json").read_text(encoding="utf-8"))

    # Historical x4 / x16 reproducibility preserved bit-for-bit
    assert sb.scale_ledger(base, 4, seed=259) == json.loads((PROJECT / "data" / "dev" / "cafe_01_x4" / "ledger.json").read_text(encoding="utf-8"))
    assert sb.scale_ledger(base, 16, seed=259) == json.loads((PROJECT / "data" / "dev" / "cafe_01_x16" / "ledger.json").read_text(encoding="utf-8"))

    for factor in (1, 4, 16, 32, 64):
        led = sb.scale_ledger(base, factor, seed=259)
        invs = [i["invoice_number"] for i in led["invoices"]]
        assert len(invs) == factor * len(base["invoices"])
        assert len(invs) == len(set(invs)), f"x{factor}: duplicate invoice_number"
        vk = [(i["vendor_id"], i["invoice_number"]) for i in led["invoices"]]
        assert len(vk) == len(set(vk)), f"x{factor}: duplicate (vendor_id, invoice_number)"

        txns = [t["txn_id"] for t in led["bank"]]
        assert len(txns) == len(set(txns)), f"x{factor}: duplicate txn_id"

        msgs = [m["msg_id"] for m in led.get("messages", [])]
        assert len(msgs) == len(set(msgs)), f"x{factor}: duplicate msg_id"

        crs = [c["credit_id"] for c in led.get("credits", [])]
        assert len(crs) == len(set(crs)), f"x{factor}: duplicate credit_id"

        pos = [i["reference_or_po"] for i in led["invoices"] if i.get("reference_or_po")]
        assert len(pos) == len(set(pos)), f"x{factor}: duplicate reference_or_po"


def test_determinism_preservation_refs_arithmetic_dates_and_forbidden_amounts():
    sb = _load_mod("scale_bundle", PROJECT / "data" / "generator" / "scale_bundle.py")
    render = _load_mod("render", PROJECT / "data" / "generator" / "render.py")
    base = json.loads((CAFE / "ledger.json").read_text(encoding="utf-8"))

    led_a = sb.scale_ledger(base, 64, seed=259)
    led_b = sb.scale_ledger(base, 64, seed=259)
    led_c = sb.scale_ledger(base, 64, seed=777)
    assert led_a == led_b
    assert led_a != led_c

    # Valid arithmetic and payment/credit links via render.validate_ledger
    render.validate_ledger(led_a)

    # Preservation of original records
    assert led_a["vendors"] == base["vendors"]
    assert led_a["credits"] == base["credits"]
    assert led_a["business"] == base["business"]
    inv_map = {i["invoice_number"]: i for i in led_a["invoices"]}
    for bi in base["invoices"]:
        assert inv_map[bi["invoice_number"]] == bi
    bank_map = {t["txn_id"]: t for t in led_a["bank"]}
    for bt in base["bank"]:
        assert bank_map[bt["txn_id"]] == bt
    msg_map = {m["msg_id"]: m for m in led_a["messages"]}
    for bm in base["messages"]:
        assert msg_map[bm["msg_id"]] == bm

    # Added records: dates < 2026-07-01, forbidden amounts excluded, valid invoice_refs
    base_invs = {i["invoice_number"] for i in base["invoices"]}
    base_txns = {t["txn_id"] for t in base["bank"]}
    base_msgs = {m["msg_id"] for m in base["messages"]}
    paid_txns = {p["txn_id"]: p for p in led_a["payments"]}
    cutoff = date(2026, 7, 1)

    for inv in led_a["invoices"]:
        if inv["invoice_number"] in base_invs:
            continue
        assert date.fromisoformat(inv["issue_date"]) < cutoff
        tot = Decimal(inv["total"])
        assert tot not in sb.FORBIDDEN_AMOUNTS
        # Full single payment before cutoff and >= issue_date
        pmts = [p for p in led_a["payments"] if p["invoice_number"] == inv["invoice_number"]]
        assert len(pmts) == 1
        assert Decimal(pmts[0]["amount_applied"]) == tot
        tx = bank_map[pmts[0]["txn_id"]]
        assert date.fromisoformat(tx["posted_on"]) < cutoff
        assert date.fromisoformat(tx["posted_on"]) >= date.fromisoformat(inv["issue_date"])

    for m in led_a["messages"]:
        for ref in m["invoice_refs"]:
            assert ref in inv_map
        if m["msg_id"] not in base_msgs:
            assert date.fromisoformat(m["received_on"]) < cutoff

    for t in led_a["bank"]:
        if t["txn_id"] in base_txns or t["txn_id"] in paid_txns:
            continue
        assert date.fromisoformat(t["posted_on"]) < cutoff
        assert abs(Decimal(t["amount"])) not in sb.FORBIDDEN_AMOUNTS


def test_reserves_pre_seeded_collisions_without_filename_overwrite(tmp_path: Path):
    sb = _load_mod("scale_bundle", PROJECT / "data" / "generator" / "scale_bundle.py")
    render = _load_mod("render", PROJECT / "data" / "generator" / "render.py")
    base = json.loads((CAFE / "ledger.json").read_text(encoding="utf-8"))

    # Simulate base bundle already containing GP-100, PO-1001, txn_1000, m005 (would collide without reservation)
    seeded = copy.deepcopy(base)
    seeded["invoices"].append({
        **copy.deepcopy(base["invoices"][4]),  # copy GP-221 template
        "invoice_number": "GP-100",
        "issue_date": "2026-07-05",
    })
    seeded["invoices"].append({
        **copy.deepcopy(base["invoices"][0]),  # copy Northside template
        "invoice_number": "NS-1080",
        "reference_or_po": "PO-1001",
        "issue_date": "2026-07-06",
    })
    seeded["bank"].append({
        "txn_id": "txn_1000",
        "posted_on": "2026-07-02",
        "amount": "-50.00",
        "currency": "USD",
        "descriptor": "MISC",
    })
    seeded["messages"].append({
        "msg_id": "m005",
        "received_on": "2026-07-03",
        "channel": "email",
        "from": "Vendor <orders@example.com>",
        "subject": "Note",
        "body": "Hello",
        "kind": "other",
        "invoice_refs": ["GP-100"],
    })

    scaled = sb.scale_ledger(seeded, 4, seed=259)
    invs = [i["invoice_number"] for i in scaled["invoices"]]
    assert len(invs) == len(set(invs))
    assert Counter(invs)["GP-100"] == 1
    assert len([t["txn_id"] for t in scaled["bank"]]) == len({t["txn_id"] for t in scaled["bank"]})
    assert len([m["msg_id"] for m in scaled["messages"]]) == len({m["msg_id"] for m in scaled["messages"]})
    pos = [i["reference_or_po"] for i in scaled["invoices"] if i.get("reference_or_po")]
    assert len(pos) == len(set(pos))

    # Render synthetic bundle to tmp_path and confirm every invoice writes a unique PDF (no overwrite)
    out_b = tmp_path / "rendered_collision_free"
    out_b.mkdir()
    (out_b / "ledger.json").write_text(json.dumps(scaled, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(CAFE / "gold.yaml", out_b / "gold.yaml")
    render.render_bundle(out_b)
    pdfs = list((out_b / "invoices").glob("*.pdf"))
    assert len(pdfs) == len(scaled["invoices"])
    assert not list((out_b / "invoices").glob("*--*.pdf"))


def test_validator_checks_existing_x16_and_detects_category_a_fault(tmp_path: Path):
    vsb = _load_mod("validate_scaled_bundle", PROJECT / "evaluation" / "validate_scaled_bundle.py")

    rep16 = vsb.validate_scaled_bundle(CAFE, PROJECT / "data" / "dev" / "cafe_01_x16")
    assert rep16["category_a_passed"] is True
    assert rep16["category_b_clean"] is True

    # Inject a Category A duplicate invoice fault into a copy of cafe_01_x4
    bad_dir = tmp_path / "bad_x4"
    shutil.copytree(PROJECT / "data" / "dev" / "cafe_01_x4", bad_dir)
    led = json.loads((bad_dir / "ledger.json").read_text(encoding="utf-8"))
    led["invoices"][0]["invoice_number"] = "GP-221"
    (bad_dir / "ledger.json").write_text(json.dumps(led, indent=2) + "\n", encoding="utf-8")

    rep_bad = vsb.validate_scaled_bundle(CAFE, bad_dir)
    assert rep_bad["category_a_passed"] is False
    assert any("duplicate invoice_numbers" in e or "GP-221" in e for e in rep_bad["category_a"]["errors"])


def test_controlled_profile_descriptors_and_observable_settlement(tmp_path: Path):
    sb = _load_mod("scale_bundle", PROJECT / "data" / "generator" / "scale_bundle.py")
    vsb = _load_mod("validate_scaled_bundle", PROJECT / "evaluation" / "validate_scaled_bundle.py")
    base = json.loads((CAFE / "ledger.json").read_text(encoding="utf-8"))

    # Ambiguity profile stays unchanged default; controlled appends exact invoice ref to added payment descriptors
    amb = sb.scale_ledger(base, 4, seed=259, profile="ambiguity")
    ctrl = sb.scale_ledger(base, 4, seed=259, profile="controlled")
    assert amb["invoices"] == ctrl["invoices"]
    assert amb["messages"] == ctrl["messages"]
    assert amb["payments"] == ctrl["payments"]

    base_txns = {t["txn_id"]: t for t in base["bank"]}
    ctrl_pay = {p["txn_id"]: p["invoice_number"] for p in ctrl["payments"]}
    ctrl_bank = {t["txn_id"]: t for t in ctrl["bank"]}
    for tid, bt in base_txns.items():
        assert ctrl_bank[tid] == bt  # original descriptors untouched
    for tid, inv_no in ctrl_pay.items():
        if tid in base_txns:
            continue
        assert inv_no in ctrl_bank[tid]["descriptor"]

    # Build a small rendered controlled bundle at x4 and verify Category A & Category B both pass cleanly
    out_ctrl = tmp_path / "ctrl_x4"
    sb.build_scaled_bundle(CAFE, 4, out_ctrl, seed=259, profile="controlled")
    rep = vsb.validate_scaled_bundle(CAFE, out_ctrl, strict_matcher=True)
    assert rep["category_a_passed"] is True
    assert rep["category_b_clean"] is True
    assert rep["category_b"]["false_open_historical_count"] == 0
    assert rep["category_b"]["tool_diffs_vs_base"] == {}
    # Historical range growth is explicitly tracked rather than hidden
    assert rep["category_b"]["historical_comparison_ranges"]["base"]["count"] == 1
    assert rep["category_b"]["historical_comparison_ranges"]["scaled"]["count"] == 9


def test_observable_collision_classifier_buckets_on_ambiguity_bundles():
    vsb = _load_mod("validate_scaled_bundle", PROJECT / "evaluation" / "validate_scaled_bundle.py")

    rep32 = vsb.validate_scaled_bundle(CAFE, PROJECT / "data" / "dev" / "cafe_01_x32")
    obs32 = rep32["category_b"]["observable_collision_classes"]
    assert obs32["unconfirmed_total"] == 6
    assert len(obs32["unique_local"]) == 0
    assert len(obs32["unique_joint"]) == 0
    assert len(obs32["not_identifiable"]) == 6

    rep64 = vsb.validate_scaled_bundle(CAFE, PROJECT / "data" / "dev" / "cafe_01_x64")
    obs64 = rep64["category_b"]["observable_collision_classes"]
    assert obs64["unconfirmed_total"] == 27
    local_invs = {x["invoice"] for x in obs64["unique_local"]}
    joint_invs = {x["invoice"] for x in obs64["unique_joint"]}
    non_id_invs = {x["invoice"] for x in obs64["not_identifiable"]}
    assert {"GP-164", "GP-218", "NS-919"}.issubset(local_invs)
    assert {"BW-560", "BW-624", "BW-591", "BW-573"}.issubset(joint_invs)
    assert {"NS-863", "NS-866", "BW-519", "BW-521", "BW-557", "BW-559"}.issubset(non_id_invs)
    assert len(local_invs) + len(joint_invs) + len(non_id_invs) == 27
