"""Generate a self-contained printable HTML sheet to hand-check gold.yaml against ledger.json.

    cd project
    python evaluation/review/make_gold_sheet.py data/dev/plumbing_01

Writes <bundle_dir>/gold_review.html.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.evaluation import QuerySuite
from cashbooks.contracts.postprocess import mask_numbers
from cashbooks.normalize.terms import derive_due_date, parse_terms

PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_QUERIES = PROJECT / "evaluation" / "queries.yaml"


def _h(val: Any) -> str:
    return html.escape("" if val is None else str(val))


def _last4(val: str | None) -> str:
    if not val:
        return "—"
    s = str(val).strip()
    return f"****{s[-4:]}" if len(s) >= 4 else s


def _invoice_facts(inv: dict, ledger: dict, eval_clock: date) -> dict[str, Any]:
    num = inv["invoice_number"]
    issue = date.fromisoformat(inv["issue_date"])
    terms = parse_terms(inv.get("payment_terms"))
    derived, _ = derive_due_date(issue, terms)
    if inv.get("stated_due_date"):
        stated = date.fromisoformat(inv["stated_due_date"])
    elif inv.get("print_due_date"):
        stated = derived
    else:
        stated = None

    txns = {t["txn_id"]: t for t in ledger.get("bank", [])}
    applied_payments = [
        {
            "txn_id": p["txn_id"],
            "amount_applied": Decimal(p["amount_applied"]),
            "posted_on": txns.get(p["txn_id"], {}).get("posted_on", ""),
            "descriptor": txns.get(p["txn_id"], {}).get("descriptor", ""),
        }
        for p in ledger.get("payments", [])
        if p["invoice_number"] == num
    ]
    applied_credits = [
        {
            "credit_id": c["credit_id"],
            "amount": Decimal(c["amount"]),
            "issued_on": c["issued_on"],
        }
        for c in ledger.get("credits", [])
        if c["invoice_number"] == num and date.fromisoformat(c["issued_on"]) <= eval_clock
    ]
    total = Decimal(inv["total"])
    paid_sum = sum((p["amount_applied"] for p in applied_payments), Decimal("0.00"))
    cred_sum = sum((c["amount"] for c in applied_credits), Decimal("0.00"))
    remaining = total - paid_sum - cred_sum
    remit = inv.get("remit") or {}
    return {
        "invoice_number": num,
        "vendor_id": inv["vendor_id"],
        "issue_date": inv["issue_date"],
        "payment_terms": inv.get("payment_terms") or "—",
        "stated_due_date": stated.isoformat() if stated else None,
        "derived_due_date": derived.isoformat() if derived else None,
        "subtotal": inv.get("subtotal"),
        "tax": inv.get("tax"),
        "total": f"{total:.2f}",
        "currency": inv["currency"],
        "remit_bank": remit.get("bank_name") or "—",
        "remit_acct": _last4(remit.get("account_number")),
        "remit_rout": _last4(remit.get("routing_number")),
        "payments": applied_payments,
        "credits": applied_credits,
        "remaining": f"{remaining:.2f}",
    }


def _render_evidence_facts(
    ev_ids: list[str],
    inv_map: dict[str, dict[str, Any]],
    txn_map: dict[str, dict[str, Any]],
    msg_map: dict[str, dict[str, Any]],
    vendor_map: dict[str, dict[str, Any]],
    credit_map: dict[str, dict[str, Any]],
) -> str:
    if not ev_ids:
        return '<div class="muted">No gold evidence IDs listed.</div>'
    blocks: list[str] = []
    for eid in ev_ids:
        if eid.startswith("inv_"):
            num = eid[4:]
            f = inv_map.get(num)
            if not f:
                blocks.append(f'<div class="fact"><b>{_h(eid)}</b>: <em>not found in ledger</em></div>')
                continue
            due_str = f"printed {f['stated_due_date']}" if f["stated_due_date"] else f"derived {f['derived_due_date']}"
            if f["stated_due_date"] and f["derived_due_date"] and f["stated_due_date"] != f["derived_due_date"]:
                due_str += f" (derived {f['derived_due_date']})"
            pay_str = ", ".join(f"{p['txn_id']} ({p['amount_applied']:.2f} on {p['posted_on']})" for p in f["payments"]) or "none"
            cred_str = ", ".join(f"{c['credit_id']} ({c['amount']:.2f} on {c['issued_on']})" for c in f["credits"]) or "none"
            blocks.append(
                f'<div class="fact"><b>{_h(eid)}</b> ({_h(f["currency"])})<br>'
                f'Issued: {_h(f["issue_date"])} · Terms: {_h(f["payment_terms"])} · Due: {_h(due_str)}<br>'
                f'Subtotal: {_h(f["subtotal"])} · Tax: {_h(f["tax"])} · Total: <b>{_h(f["total"])}</b> · '
                f'Remaining: <b>{_h(f["remaining"])} {_h(f["currency"])}</b><br>'
                f'Remit: {_h(f["remit_bank"])}, acct {_h(f["remit_acct"])}, rout {_h(f["remit_rout"])}<br>'
                f'Payments: {_h(pay_str)} · Credits: {_h(cred_str)}</div>'
            )
        elif eid.startswith("txn_"):
            tx = txn_map.get(eid)
            if not tx:
                blocks.append(f'<div class="fact"><b>{_h(eid)}</b>: <em>not found in ledger</em></div>')
                continue
            blocks.append(
                f'<div class="fact"><b>{_h(eid)}</b> (bank row): '
                f'{_h(tx["posted_on"])} · <b>{_h(tx["amount"])} {_h(tx["currency"])}</b> · '
                f'{_h(mask_numbers(tx["descriptor"]))}</div>'
            )
        elif eid.startswith("msg_"):
            mid = eid[4:]
            m = msg_map.get(mid)
            if not m:
                blocks.append(f'<div class="fact"><b>{_h(eid)}</b>: <em>not found in ledger</em></div>')
                continue
            snippet = mask_numbers(m.get("body", ""))[:300]
            blocks.append(
                f'<div class="fact"><b>{_h(eid)}</b> (message): '
                f'From: {_h(m.get("from"))} · Date: {_h(m.get("received_on"))}<br>'
                f'<span class="snippet">{_h(snippet)}</span></div>'
            )
        elif eid.startswith("vh_"):
            vid = eid[3:]
            v = vendor_map.get(vid)
            if not v:
                blocks.append(f'<div class="fact"><b>{_h(eid)}</b>: <em>not found in ledger</em></div>')
                continue
            vp = v.get("verified_payment") or {}
            blocks.append(
                f'<div class="fact"><b>{_h(eid)}</b> (verified vendor): '
                f'{_h(v["canonical_name"])} · {_h(vp.get("bank_name"))} acct {_h(_last4(vp.get("account_number")))} '
                f'(verified {_h(vp.get("verified_on"))}) · Contact: {_h(v.get("trusted_contact"))}</div>'
            )
        elif eid.startswith("cn_"):
            cid = eid[3:]
            c = credit_map.get(cid)
            if not c:
                blocks.append(f'<div class="fact"><b>{_h(eid)}</b>: <em>not found in ledger</em></div>')
                continue
            blocks.append(
                f'<div class="fact"><b>{_h(eid)}</b> (credit note): '
                f'Invoice {_h(c["invoice_number"])} · Amount <b>{_h(c["amount"])}</b> · '
                f'Issued {_h(c["issued_on"])} · {_h(c.get("reason", ""))}</div>'
            )
        else:
            blocks.append(f'<div class="fact"><b>{_h(eid)}</b></div>')
    return "\n".join(blocks)


def render_gold_html(bundle_dir: Path, queries_path: Path = DEFAULT_QUERIES) -> str:
    ledger = json.loads((bundle_dir / "ledger.json").read_text(encoding="utf-8"))
    gold = yaml.safe_load((bundle_dir / "gold.yaml").read_text(encoding="utf-8"))
    suite = QuerySuite.model_validate(yaml.safe_load(queries_path.read_text(encoding="utf-8")))
    specs = {c.id: c for c in suite.conversations}

    biz = ledger["business"]
    eval_clock = date.fromisoformat(biz["evaluation_clock"])
    vendor_map = {v["vendor_id"]: v for v in ledger["vendors"]}
    inv_facts = [_invoice_facts(inv, ledger, eval_clock) for inv in ledger["invoices"]]
    inv_map = {f["invoice_number"]: f for f in inv_facts}
    txn_map = {t["txn_id"]: t for t in ledger.get("bank", [])}
    msg_map = {m["msg_id"]: m for m in ledger.get("messages", [])}
    credit_map = {c["credit_id"]: c for c in ledger.get("credits", [])}

    vendor_rows = []
    for v in ledger["vendors"]:
        vp = v.get("verified_payment") or {}
        aliases = ", ".join(a["alias"] for a in v.get("aliases", [])) or "—"
        vendor_rows.append(
            f"<tr><td><code>{_h(v['vendor_id'])}</code></td><td>{_h(v['canonical_name'])}</td>"
            f"<td>{_h(aliases)}</td><td>{_h(vp.get('bank_name'))}</td>"
            f"<td>{_h(_last4(vp.get('account_number')))}</td><td>{_h(_last4(vp.get('routing_number')))}</td>"
            f"<td>{_h(vp.get('verified_on'))}</td><td>{_h(v.get('trusted_contact'))}</td></tr>"
        )

    inv_rows = []
    for f in inv_facts:
        due = f["stated_due_date"] or f["derived_due_date"] or "—"
        inv_rows.append(
            f"<tr><td><code>{_h(f['invoice_number'])}</code></td>"
            f"<td>{_h(vendor_map.get(f['vendor_id'], {}).get('canonical_name', f['vendor_id']))}</td>"
            f"<td>{_h(f['issue_date'])}</td><td>{_h(f['payment_terms'])}</td><td>{_h(due)}</td>"
            f"<td>{_h(f['total'])} {_h(f['currency'])}</td>"
            f"<td><b>{_h(f['remaining'])} {_h(f['currency'])}</b></td>"
            f"<td>{_h(f['remit_bank'])} {_h(f['remit_acct'])}</td></tr>"
        )

    conv_sections: list[str] = []
    for qid, g_entry in gold.items():
        if qid not in specs:
            continue
        spec = specs[qid]
        setup_override = g_entry.get("setup_text") if isinstance(g_entry, dict) else None
        g_turns = g_entry["turns"] if isinstance(g_entry, dict) else g_entry

        turn_blocks: list[str] = []
        gi = 0
        for ti, turn in enumerate(spec.turns):
            if not turn.scored:
                setup_txt = setup_override if (ti == 0 and setup_override) else turn.text
                turn_blocks.append(
                    f'<div class="setup"><b>Turn {ti} (unscored setup):</b> {_h(setup_txt)}</div>'
                )
                continue
            g = g_turns[gi] if gi < len(g_turns) else {}
            gi += 1
            turn_text = g.get("text") or turn.text
            values = g.get("values") or {}
            ev_ids = list(g.get("evidence") or [])
            must_not = list(turn.must_not) + list(g.get("must_not") or [])

            vals_html = ", ".join(f"<code>{_h(k)}</code>: <b>{_h(v)}</b>" for k, v in values.items()) or "—"
            ev_html = ", ".join(f"<code>{_h(e)}</code>" for e in ev_ids) or "—"
            mn_html = ", ".join(f"<code>{_h(m)}</code>" for m in must_not) or "—"
            facts_html = _render_evidence_facts(ev_ids, inv_map, txn_map, msg_map, vendor_map, credit_map)

            turn_blocks.append(
                f"""<div class="turn-grid">
  <div class="gold-col">
    <div class="turn-hdr">Turn {ti} · <span class="badge">{_h(turn.expected.value)}</span></div>
    <p class="qtext">{_h(turn_text)}</p>
    <p class="beh"><b>Expected behavior:</b> {_h(turn.expected_behavior)}</p>
    <p><b>Gold values:</b> {vals_html}</p>
    <p><b>Evidence IDs:</b> {ev_html}</p>
    <p><b>Must not:</b> {mn_html}</p>
    <div class="check-row">
      <label><input type="checkbox"> Correct?</label>
      <input type="text" class="note-box" placeholder="Notes...">
    </div>
  </div>
  <div class="ledger-col">
    <div class="turn-hdr">Ledger Facts</div>
    {facts_html}
  </div>
</div>"""
            )

        conv_sections.append(
            f'<section class="conv"><h3>{_h(qid)} · {_h(", ".join(spec.labels))}</h3>'
            + "\n".join(turn_blocks)
            + "</section>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Gold Review — {_h(biz['name'])} ({_h(biz['business_id'])})</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #111; font-size: 13px; }}
  h1, h2, h3 {{ margin: 12px 0 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 16px; font-size: 12px; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 6px; text-align: left; }}
  th {{ background: #f4f4f6; }}
  code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 3px; font-size: 12px; }}
  .conv {{ border-top: 2px solid #333; padding-top: 8px; margin-top: 16px; page-break-inside: avoid; }}
  .setup {{ background: #f8fafc; border: 1px dashed #cbd5e1; padding: 6px 8px; margin-bottom: 8px; }}
  .turn-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; border: 1px solid #d1d5db; padding: 10px; margin-bottom: 10px; border-radius: 4px; }}
  .turn-hdr {{ font-weight: 600; margin-bottom: 4px; }}
  .badge {{ background: #e0f2fe; color: #075985; padding: 1px 6px; border-radius: 8px; font-size: 11px; }}
  .qtext {{ font-weight: 600; margin: 4px 0; }}
  .beh, .gold-col p {{ margin: 3px 0; }}
  .fact {{ background: #f9fafb; border: 1px solid #e5e7eb; padding: 6px; margin-bottom: 6px; border-radius: 3px; line-height: 1.4; }}
  .snippet {{ color: #374151; font-style: italic; }}
  .muted {{ color: #6b7280; }}
  .check-row {{ margin-top: 8px; display: flex; gap: 8px; align-items: center; }}
  .note-box {{ flex: 1; padding: 4px 6px; border: 1px solid #cbd5e1; border-radius: 3px; }}
  @media print {{ body {{ margin: 10px; }} .conv {{ page-break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>Gold Review: {_h(biz['name'])} (<code>{_h(biz['business_id'])}</code>)</h1>
<p><b>Type:</b> {_h(biz.get('type'))} · <b>Evaluation clock:</b> <code>{_h(biz['evaluation_clock'])}</code> · <b>Date order:</b> {_h(biz.get('date_order'))}</p>

<h2>Vendors (verified details)</h2>
<table>
  <thead><tr><th>ID</th><th>Name</th><th>Aliases</th><th>Bank</th><th>Account</th><th>Routing</th><th>Verified on</th><th>Trusted contact</th></tr></thead>
  <tbody>{''.join(vendor_rows)}</tbody>
</table>

<h2>Invoices</h2>
<table>
  <thead><tr><th>Invoice</th><th>Vendor</th><th>Issue date</th><th>Terms</th><th>Due date</th><th>Total</th><th>Remaining ({_h(biz['evaluation_clock'])})</th><th>Remit to</th></tr></thead>
  <tbody>{''.join(inv_rows)}</tbody>
</table>

<h2>Conversations</h2>
{''.join(conv_sections)}
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    a = ap.parse_args(argv)

    html_text = render_gold_html(a.bundle, a.queries)
    out = a.bundle / "gold_review.html"
    out.write_text(html_text, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
