"""Unit tests for evaluation/review/make_gold_sheet.py."""

from __future__ import annotations

import html
import importlib.util
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "make_gold_sheet", PROJECT / "evaluation" / "review" / "make_gold_sheet.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_gold_sheet"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_render_gold_html_cafe_and_plumbing():
    mod = _load_mod()
    for bname in ("cafe_01", "plumbing_01"):
        bdir = PROJECT / "data" / "dev" / bname
        ledger = json.loads((bdir / "ledger.json").read_text(encoding="utf-8"))
        html_out = mod.render_gold_html(bdir)
        assert html.escape(ledger["business"]["name"]) in html_out
        assert ledger["business"]["evaluation_clock"] in html_out
        assert 'type="checkbox"' in html_out
        assert 'class="note-box"' in html_out
        for v in ledger["vendors"]:
            vp = v.get("verified_payment") or {}
            if vp.get("account_number"):
                assert vp["account_number"] not in html_out
                assert vp["account_number"][-4:] in html_out
            if vp.get("routing_number"):
                assert vp["routing_number"] not in html_out
        for inv in ledger["invoices"]:
            assert inv["invoice_number"] in html_out
            remit = inv.get("remit") or {}
            if remit.get("account_number"):
                assert remit["account_number"] not in html_out

    # Verify plumbing_01 Q21 setup_text override and Q02 turn text override are rendered
    plumb_html = mod.render_gold_html(PROJECT / "data" / "dev" / "plumbing_01")
    assert "List my Crestline bills from July and August, oldest first." in plumb_html
    assert "How much do I owe Crestline Pipe &amp; Supply as of September 30?" in plumb_html
