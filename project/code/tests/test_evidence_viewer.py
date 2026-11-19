"""Offline tests for the read-only evidence viewer endpoint, redaction, and highlighting."""

from __future__ import annotations

import io
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pdfplumber
import pytest
from PIL import Image

from cashbooks.demo.web import (
    PROJECT,
    DemoService,
    _locate_span_box,
    make_server,
)


@pytest.fixture
def http_app():
    app = DemoService(mode="rehearsal")
    server = make_server(0, service=app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield app, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    for sid in list(app.sessions):
        app.discard(sid)


def _get(url: str):
    return urllib.request.urlopen(urllib.request.Request(url))


def _post(url: str, body: dict, token: str):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-CashBooks-Token": token},
    )
    return json.load(urllib.request.urlopen(req))


def _boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def test_ns1048_total_highlight_overlaps_total_amount_and_page_span_has_no_box(http_app):
    app, url = http_app
    sid = app.create("C3")
    res = _post(f"{url}/api/ask", {"session": sid, "question": "Did I already pay invoice NS-1048?"}, app.token)
    ids = {s["evidence_id"] for s in res["sources"]}
    assert "span_inv_NS-1048_total" in ids

    meta = json.load(_get(f"{url}/api/evidence?session={urllib.parse.quote(sid)}&id=span_inv_NS-1048_total"))
    assert meta["kind"] == "pdf_page"
    assert meta["dpi"] >= 200
    assert meta["title"] == "Invoice NS-1048 · page 1 · Total due"
    assert meta["supports"]
    hl = meta["highlight"]
    assert hl is not None

    with pdfplumber.open(PROJECT / "data/dev/cafe_01/invoices/NS-1048.pdf") as pdf:
        pg = pdf.pages[0]
        scale = meta["width"] / float(pg.width)
        hl_pt = (hl["px_x0"] / scale, hl["px_top"] / scale, hl["px_x1"] / scale, hl["px_bottom"] / scale)
        amt_hits = pg.search(r"\$842\.00")
        tot_hits = pg.search("Total")
        assert amt_hits and tot_hits
        amt_box = (amt_hits[0]["x0"], amt_hits[0]["top"], amt_hits[0]["x1"], amt_hits[0]["bottom"])
        tot_box = (tot_hits[0]["x0"], tot_hits[0]["top"], tot_hits[0]["x1"], tot_hits[0]["bottom"])
        assert abs(amt_box[1] - tot_box[1]) < 2.0  # $842.00 is on the Total line
        assert _boxes_overlap(hl_pt, amt_box)

    png_bytes = _get(url + meta["image_url"]).read()
    im = Image.open(io.BytesIO(png_bytes))
    assert im.format == "PNG"
    assert im.size == (meta["width"], meta["height"])

    # Page-level span shows page with no highlight box.
    page_meta = json.load(_get(f"{url}/api/evidence?session={urllib.parse.quote(sid)}&id=span_inv_NS-1048_p1"))
    assert page_meta["kind"] == "pdf_page"
    assert page_meta["highlight"] is None
    assert page_meta["title"] == "Invoice NS-1048 · page 1"


def test_duplicate_amount_disambiguation_prefers_total_label_without_offsets():
    app = DemoService()
    cached = app._cached_pdf_page("invoices/BW-760.pdf", 1)
    # "$486.00" appears on both Subtotal and Amount due lines; without offsets it must pick Total/Amount due.
    box = _locate_span_box(cached, "total", "$486.00", None, None)
    assert box is not None
    with pdfplumber.open(PROJECT / "data/dev/cafe_01/invoices/BW-760.pdf") as pdf:
        pg = pdf.pages[0]
        due_hits = pg.search("Amount due")
        assert due_hits
        due_y = (due_hits[0]["top"] + due_hits[0]["bottom"]) / 2.0
        box_y = (box[1] + box[3]) / 2.0
        assert abs(box_y - due_y) < 3.0


def test_redaction_covers_every_six_plus_digit_run_and_blacks_out_image_pixels(http_app):
    app, url = http_app
    pdf_files = sorted((PROJECT / "data/dev/cafe_01/invoices").glob("*.pdf")) + sorted(
        (PROJECT / "data/dev/cafe_01/credits").glob("*.pdf")
    )
    for pdf_path in pdf_files:
        stem = pdf_path.stem
        kind = "inv" if pdf_path.parent.name == "invoices" else "cn"
        eid = f"span_{kind}_{stem}_p1"
        png = _get(f"{url}/api/evidence/page?id={eid}").read()
        im = Image.open(io.BytesIO(png)).convert("RGB")
        rel = str(pdf_path.relative_to(PROJECT / "data/dev/cafe_01"))
        cached = app._cached_pdf_page(rel, 1)

        with pdfplumber.open(pdf_path) as pdf:
            pg = pdf.pages[0]
            tm = pg.get_textmap()
            runs = list(re.finditer(r"\d{6,}", tm.as_string))
            for m in runs:
                chars = [c for _, c in tm.tuples[m.start():m.end()] if c is not None]
                redact_chars = chars[:-4]
                kept_chars = chars[-4:]
                # Verify redaction box exists covering every digit except the last 4.
                for ch in redact_chars:
                    assert any(
                        rb[0] <= ch["x0"] + 0.1
                        and rb[1] <= ch["top"] + 0.1
                        and rb[2] >= ch["x1"] - 0.1
                        and rb[3] >= ch["bottom"] - 0.1
                        for rb in cached.redaction_boxes_pt
                    ), f"missing redaction box in {pdf_path.name}"

                # Verify pixels inside the redacted region are black in the served PNG.
                rx0 = int(min(c["x0"] for c in redact_chars) * cached.scale) + 1
                ry0 = int(min(c["top"] for c in redact_chars) * cached.scale) + 1
                rx1 = int(max(c["x1"] for c in redact_chars) * cached.scale) - 1
                ry1 = int(max(c["bottom"] for c in redact_chars) * cached.scale) - 1
                crop = im.crop((rx0, ry0, max(rx0 + 1, rx1), max(ry0 + 1, ry1)))
                assert set(crop.tobytes()) == {0}, f"non-black pixel in redaction box of {pdf_path.name}"

                # Verify the last 4 digits are NOT covered by a solid black box.
                kx0 = int(min(c["x0"] for c in kept_chars) * cached.scale)
                ky0 = int(min(c["top"] for c in kept_chars) * cached.scale)
                kx1 = int(max(c["x1"] for c in kept_chars) * cached.scale)
                ky1 = int(max(c["bottom"] for c in kept_chars) * cached.scale)
                kept_crop = im.crop((kx0, ky0, kx1, ky1))
                assert any(b != 0 for b in kept_crop.tobytes()), f"last 4 digits clipped in {pdf_path.name}"

    # Highlighting an account field (BW-771) must still keep the redacted prefix solid black.
    remit_png = _get(f"{url}/api/evidence/page?id=span_inv_BW-771_remit_account").read()
    remit_im = Image.open(io.BytesIO(remit_png)).convert("RGB")
    cached_bw = app._cached_pdf_page("invoices/BW-771.pdf", 1)
    rb = cached_bw.redaction_boxes_pt[0]
    rcrop = remit_im.crop((
        int(rb[0] * cached_bw.scale) + 1,
        int(rb[1] * cached_bw.scale) + 1,
        int(rb[2] * cached_bw.scale) - 1,
        int(rb[3] * cached_bw.scale) - 1,
    ))
    assert set(rcrop.tobytes()) == {0}


def test_pdf_pages_are_cached_in_memory(monkeypatch):
    app = DemoService()
    calls = 0
    from cashbooks.demo import web as web_mod

    orig = web_mod._render_redacted_base_page

    def counting_render(pdf_path, page_num, dpi=web_mod.PDF_DPI):
        nonlocal calls
        calls += 1
        return orig(pdf_path, page_num, dpi=dpi)

    monkeypatch.setattr(web_mod, "_render_redacted_base_page", counting_render)
    app.render_evidence_png("span_inv_NS-1048_total")
    app.render_evidence_png("span_inv_NS-1048_p1")
    app.get_evidence("span_inv_NS-1048_subtotal")
    assert calls == 1


def test_bank_message_and_vendor_card_rendering_and_masking(http_app):
    app, url = http_app
    sid = app.create("C3")

    # Bank row
    bank = json.load(_get(f"{url}/api/evidence?session={urllib.parse.quote(sid)}&id=txn_0193"))
    assert bank["kind"] == "bank"
    assert bank["highlighted_id"] == "txn_0193"
    highlighted = [r for r in bank["rows"] if r["highlighted"]]
    assert len(highlighted) == 1 and highlighted[0]["amount"] == "-842.00"
    assert len(bank["rows"]) >= 3
    assert not re.search(r"\b\d{6,}\b", json.dumps(bank))

    # Message (m01 has raw account/routing digits in messages.jsonl -> must be masked)
    msg1 = json.load(_get(f"{url}/api/evidence?session={urllib.parse.quote(sid)}&id=span_msg_m01"))
    assert msg1["kind"] == "message"
    assert "008812345507" not in json.dumps(msg1)
    assert "091000019" not in json.dumps(msg1)
    assert "5507" in msg1["body"]

    msg3 = json.load(_get(f"{url}/api/evidence?session={urllib.parse.quote(sid)}&id=msg_m03&supports=GP-228+paid+in+full"))
    assert msg3["kind"] == "message"
    assert msg3["received_on"] == "2026-09-15"
    assert "GP-228" in msg3["body"][msg3["highlight_start"]:msg3["highlight_end"]]

    # Vendor card (via rehearsal BW-771 turn so supports text highlights account)
    _post(f"{url}/api/ask", {"session": sid, "question": "Did the payment details on BW-771 change?"}, app.token)
    vh = json.load(_get(f"{url}/api/evidence?session={urllib.parse.quote(sid)}&id=vh_v_beanworks"))
    assert vh["kind"] == "vendor"
    assert vh["highlighted_field"] == "account"
    assert vh["vendor"]["account"] == "****4417"
    assert "002299104417" not in json.dumps(vh)
    assert "322271627" not in json.dumps(vh)

    vh_contact = json.load(_get(f"{url}/api/evidence?id=vh_v_northside_contact"))
    assert vh_contact["highlighted_field"] == "trusted_contact"
    assert "Dana Ruiz" in vh_contact["vendor"]["trusted_contact"]


def test_unknown_id_and_path_traversal_are_rejected(http_app):
    _, url = http_app
    bad_ids = [
        "span_inv_DOES-NOT-EXIST_total",
        "txn_9999",
        "vh_v_unknown",
        "span_msg_m99",
        "../../code/.env",
        "../plumbing_01/ledger.json",
        "span_inv_../../code/.env_total",
        "span_inv_..%2F..%2Fcode%2F.env_total",
        "../../README.md",
    ]
    for bid in bad_ids:
        for route in ("/api/evidence", "/api/evidence/page"):
            with pytest.raises(urllib.error.HTTPError) as exc:
                _get(f"{url}{route}?id={urllib.parse.quote(bid, safe='')}")
            assert exc.value.code == 404
            payload = json.loads(exc.value.read().decode())
            assert payload == {"error": "not found in records"}
