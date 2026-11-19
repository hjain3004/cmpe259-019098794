"""Local web interface for the existing assistant. No evaluation or prompt changes."""

from __future__ import annotations

import argparse
import hmac
import io
import json
import math
import mimetypes
import re
import secrets
import sqlite3
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import pdfplumber
from PIL import Image, ImageDraw

from cashbooks.contracts.postprocess import mask_numbers
from cashbooks.demo.rehearsal import rehearsal_llm
from cashbooks.demo.session import ChatSession, ChatTurnResult
from cashbooks.ingest.bank_csv import read_bank_csv
from cashbooks.ingest.bundle import read_messages, read_vendor_history
from cashbooks.store.db import Store
from cashbooks.store.load_gold import load_gold

PROJECT = Path(__file__).resolve().parents[4]
PDF_DPI = 216  # >= 200 dpi (3x PDF 72-pt scale)
_VALID_EID = re.compile(r"^(?:span|txn|vh|msg)_[A-Za-z0-9_-]+$")
_PAGE_SPAN_RE = re.compile(r"^span_(inv|cn)_([A-Za-z0-9-]+?)_p(\d+)(?:_w\d+)?$")
_FIELD_SPAN_RE = re.compile(r"^span_(inv|cn)_([A-Za-z0-9-]+?)_([A-Za-z0-9_]+)$")
_MSG_ID_RE = re.compile(r"^(?:span_)?msg_([A-Za-z0-9_-]+)$")
_VH_ID_RE = re.compile(r"^vh_(v_[A-Za-z0-9-]+?)(?:_(account|routing|bank|bank_name|contact|trusted_contact|aliases|alias|verified_on))?$")
_DIGIT_RUN_RE = re.compile(r"\d{6,}")

_FIELD_LABELS = {
    "total": ("Total Due", "Amount due", "Invoice total", "Credit amount", "Total"),
    "currency": ("Total Due", "Amount due", "Invoice total", "Total"),
    "subtotal": ("Subtotal",),
    "tax": ("Sales tax", "Tax"),
    "invoice_number": ("Invoice No", "Invoice #", "Number"),
    "issue_date": ("Invoice Date", "Issued", "Date"),
    "stated_due_date": ("Due Date", "Due date", "Due"),
    "payment_terms": ("Payment terms", "Terms"),
    "reference_or_po": ("PO:", "Ref:"),
    "remit_bank_name": ("Bank:", "Remit payment to"),
    "remit_account": ("Account:", "Remit payment to"),
    "remit_routing": ("Routing:", "Remit payment to"),
    "credit_id": ("Credit No",),
    "invoice_ref": ("Applies to invoice",),
    "memo": ("Memo:", "Note:"),
}

_FIELD_TITLES = {
    "total": "Total due",
    "subtotal": "Subtotal",
    "tax": "Tax",
    "currency": "Currency",
    "invoice_number": "Invoice number",
    "issue_date": "Issue date",
    "stated_due_date": "Due date",
    "payment_terms": "Payment terms",
    "reference_or_po": "PO / Reference",
    "remit_bank_name": "Remit bank",
    "remit_account": "Remit account",
    "remit_routing": "Remit routing",
    "vendor_name": "Vendor name",
    "memo": "Memo",
    "credit_id": "Credit number",
    "invoice_ref": "Invoice reference",
}

CONFIGS = {
    "C3": ("Tools + records", "Claude uses read-only tools to compute answers from extracted records."),
    "C0": ("Full context", "Claude receives the complete document collection in its prompt."),
    "C1": ("Document search", "BM25 selects raw document passages for Claude to read."),
    "C2": ("Record search", "BM25 selects structured records for Claude to read."),
    "C4": ("Tools + checked records", "A reference configuration uses hand-checked records instead of extracted records."),
}
TOOLS = {
    "list_open_bills": ("Find outstanding bills", "Looked up open bills and their due dates."),
    "get_bill_status": ("Check the bill's status", "Calculated the balance using recorded payments and credits."),
    "match_payments": ("Find matching payments", "Checked bank transactions for confirmed or possible matches."),
    "sum_amount_due": ("Calculate the amount due", "Added outstanding balances, keeping currencies separate."),
    "compare_vendor_payment_details": ("Compare payment details", "Compared the invoice with the trusted vendor record."),
    "summarize_purchases": ("Summarize purchases", "Calculated quantities and spending for the requested period."),
    "get_source_evidence": ("Look up supporting evidence", "Retrieved the source material behind the cited records."),
}
QUESTIONS = [
    {"title": "Check a payment", "question": "Did I already pay invoice NS-1048?"},
    {"title": "Review payment details", "question": "Did the payment details on BW-771 change?"},
    {"title": "Plan the week", "question": "What bills are due in the next seven days?"},
]


class EvidenceNotFoundError(LookupError):
    """Raised when an evidence ID is unknown, out of bundle, or unsafe."""


@dataclass
class CachedPdfPage:
    redacted_image: Image.Image
    width_pt: float
    height_pt: float
    scale: float
    tm_string: str
    tm_tuples: list
    redaction_boxes_pt: list[tuple[float, float, float, float]]
    plain_png: bytes | None = None


def source_label(eid: str) -> str:
    for prefix, label in (("span_inv_", "Invoice"), ("span_cn_", "Credit note")):
        if eid.startswith(prefix):
            return f"{label} {eid[len(prefix):].split('_')[0]}"
    if eid.startswith("txn_"):
        return "Bank transaction"
    if eid.startswith("vh_"):
        return "Trusted vendor record"
    if eid.startswith("span_msg_") or eid.startswith("msg_"):
        return "Vendor message"
    return "Supporting record"


def _field_human_title(field_name: str) -> str:
    if field_name in _FIELD_TITLES:
        return _FIELD_TITLES[field_name]
    if field_name.startswith("line") and field_name[4:].isdigit():
        return f"Line item {field_name[4:]}"
    return field_name.replace("_", " ").capitalize()


def present_result(result: ChatTurnResult, mode: str) -> dict:
    """Publish a narrow, masked view. Raw documents and tool JSON stay off the UI."""
    trace = []
    for call in result.tool_calls:
        title, explanation = TOOLS.get(call.name, ("Read business records", "Requested information from a read-only tool."))
        try:
            failed = "error" in json.loads(call.result_preview)
        except (ValueError, TypeError):
            failed = call.result_preview.lstrip().startswith('{"error":')
        args = []
        for key in ("invoice_number", "bill_id", "vendor", "as_of", "date_from", "date_to", "due_before", "item"):
            if call.args.get(key) is not None:
                args.append(f"{key.replace('_', ' ')}: {mask_numbers(str(call.args[key]))}")
        trace.append({"name": call.name, "title": title, "description": explanation,
                      "details": "; ".join(args), "failed": failed})
    citations = []
    seen = set()
    for c in result.citations:
        key = (c.evidence_id, c.supports)
        if key not in seen:
            citations.append({
                "evidence_id": c.evidence_id,
                "label": source_label(c.evidence_id),
                "supports": mask_numbers(c.supports),
            })
            seen.add(key)
    valid = result.response is not None
    return {
        "ok": valid, "config": result.config_name, "mode": mode,
        "kind": result.answerability.value if result.answerability else "ERROR",
        "answer": mask_numbers(result.answer) if valid else "The assistant did not return a valid answer. Your question has not been answered. Try again or start a new conversation.",
        "clarifying_question": mask_numbers(result.clarifying_question or ""),
        "next_step": mask_numbers(result.next_step or ""),
        "risks": [mask_numbers(r) for r in result.risk_indicators],
        "calculation": {"steps": [mask_numbers(s) for s in result.calculation_steps], "result": mask_numbers(result.calculation_result or "")},
        "sources": citations, "tools": trace,
        "retrieved_count": len(result.retrieved_chunks),
        "latency_ms": result.latency_ms if mode == "live" else None,
    }


def _chars_bbox(chars: list[dict]) -> tuple[float, float, float, float] | None:
    if not chars:
        return None
    return (
        min(float(c["x0"]) for c in chars),
        min(float(c["top"]) for c in chars),
        max(float(c["x1"]) for c in chars),
        max(float(c["bottom"]) for c in chars),
    )


def _quote_to_regex(quote: str) -> str:
    """Convert a stored (possibly masked) quote into a regex tolerating whitespace and masked digits."""
    parts = []
    for token in re.split(r"(\*+|\s+)", quote.strip()):
        if not token:
            continue
        if token.isspace():
            parts.append(r"\s+")
        elif set(token) == {"*"}:
            parts.append(r"\d+")
        else:
            parts.append(re.escape(token))
    return "(?s)" + "".join(parts)


def _norm_ws(s: str) -> str:
    return " ".join(s.split())


def _box_distance(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax = (a[0] + a[2]) / 2.0
    ay = (a[1] + a[3]) / 2.0
    bx = (b[0] + b[2]) / 2.0
    by = (b[1] + b[3]) / 2.0
    return math.hypot(ax - bx, (ay - by) * 3.0)


def _find_matches_in_textmap(
    tm_string: str, tm_tuples: list, pattern: str
) -> list[tuple[int, int, tuple[float, float, float, float]]]:
    out = []
    for m in re.finditer(pattern, tm_string):
        chars = [c for _, c in tm_tuples[m.start():m.end()] if c is not None]
        bbox = _chars_bbox(chars)
        if bbox is not None:
            out.append((m.start(), m.end(), bbox))
    return out


def _locate_span_box(
    cached: CachedPdfPage,
    field_name: str,
    quote_text: str | None,
    start: int | None,
    end: int | None,
) -> tuple[float, float, float, float] | None:
    tm_str = cached.tm_string
    tm_tuples = cached.tm_tuples

    if start is not None and end is not None and 0 <= start < end <= len(tm_str):
        slice_text = tm_str[start:end]
        if quote_text is None or _norm_ws(mask_numbers(slice_text)) == _norm_ws(quote_text) or _norm_ws(slice_text) == _norm_ws(quote_text):
            chars = [c for _, c in tm_tuples[start:end] if c is not None]
            bbox = _chars_bbox(chars)
            if bbox is not None:
                return bbox

    if not quote_text or not quote_text.strip():
        return None

    matches = _find_matches_in_textmap(tm_str, tm_tuples, _quote_to_regex(quote_text))
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0][2]

    if start is not None and end is not None and end > start:
        target_mid = (start + end) / 2.0
        return min(matches, key=lambda m: abs(((m[0] + m[1]) / 2.0) - target_mid))[2]

    labels = _FIELD_LABELS.get(field_name, ())
    label_boxes: list[tuple[float, float, float, float]] = []
    for lbl in labels:
        for _, _, lbox in _find_matches_in_textmap(tm_str, tm_tuples, re.escape(lbl)):
            label_boxes.append(lbox)
    if label_boxes:
        return min(matches, key=lambda m: min(_box_distance(m[2], lb) for lb in label_boxes))[2]

    return matches[0][2]


def _render_redacted_base_page(pdf_path: Path, page_num: int, dpi: int = PDF_DPI) -> CachedPdfPage:
    with pdfplumber.open(str(pdf_path)) as pdf:
        if not 1 <= page_num <= len(pdf.pages):
            raise EvidenceNotFoundError("not found in records")
        page = pdf.pages[page_num - 1]
        tm = page.get_textmap()
        im = page.to_image(resolution=dpi).original.convert("RGB")
        scale = im.width / float(page.width)

        redaction_boxes_pt: list[tuple[float, float, float, float]] = []
        for m in _DIGIT_RUN_RE.finditer(tm.as_string):
            chars = [c for _, c in tm.tuples[m.start():m.end()] if c is not None]
            redact_chars = chars[:-4]
            if not redact_chars:
                continue
            bbox = _chars_bbox(redact_chars)
            if bbox is not None:
                redaction_boxes_pt.append(bbox)

        if redaction_boxes_pt:
            draw = ImageDraw.Draw(im)
            for x0, top, x1, bottom in redaction_boxes_pt:
                draw.rectangle(
                    [x0 * scale - 1, top * scale - 2, x1 * scale, bottom * scale + 2],
                    fill=(0, 0, 0),
                )

        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return CachedPdfPage(
            redacted_image=im,
            width_pt=float(page.width),
            height_pt=float(page.height),
            scale=scale,
            tm_string=tm.as_string,
            tm_tuples=list(tm.tuples),
            redaction_boxes_pt=redaction_boxes_pt,
            plain_png=buf.getvalue(),
        )


def _render_highlighted_png(cached: CachedPdfPage, box_pt: tuple[float, float, float, float] | None) -> bytes:
    if box_pt is None:
        if cached.plain_png is not None:
            return cached.plain_png
        buf = io.BytesIO()
        cached.redacted_image.save(buf, format="PNG")
        return buf.getvalue()

    s = cached.scale
    pad = 5.0 * s
    rx0 = max(0.0, box_pt[0] * s - pad)
    ry0 = max(0.0, box_pt[1] * s - pad)
    rx1 = min(float(cached.redacted_image.width - 1), box_pt[2] * s + pad)
    ry1 = min(float(cached.redacted_image.height - 1), box_pt[3] * s + pad)

    base = cached.redacted_image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([rx0, ry0, rx1, ry1], fill=(245, 176, 40, 46), outline=(217, 119, 6, 240), width=4)
    combined = Image.alpha_composite(base, overlay).convert("RGB")

    # Keep redacted boxes pure black even when a highlight overlaps an account/routing field.
    if cached.redaction_boxes_pt:
        rdraw = ImageDraw.Draw(combined)
        for x0, top, x1, bottom in cached.redaction_boxes_pt:
            rdraw.rectangle(
                [x0 * s - 1, top * s - 2, x1 * s, bottom * s + 2],
                fill=(0, 0, 0),
            )

    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    return buf.getvalue()


def _sentence_highlight_range(masked_body: str, quote_text: str | None, supports: str) -> tuple[int, int]:
    """Return [start, end] character offsets in `masked_body` for the cited sentence."""
    if quote_text and quote_text.strip() and _norm_ws(quote_text) != _norm_ws(masked_body):
        idx = masked_body.find(quote_text)
        if idx != -1:
            return idx, idx + len(quote_text)
        parts = [re.escape(p) for p in quote_text.split()]
        m = re.search(r"\s+".join(parts), masked_body)
        if m:
            return m.start(), m.end()

    sentences: list[tuple[int, int, str]] = []
    for m in re.finditer(r"[^\n.!?]+(?:[.!?]+|$)", masked_body):
        s_txt = m.group().strip()
        if s_txt:
            lead = len(m.group()) - len(m.group().lstrip())
            start = m.start() + lead
            end = start + len(s_txt)
            sentences.append((start, end, s_txt))

    if not sentences:
        return 0, len(masked_body)

    stop = {"the", "and", "for", "that", "this", "with", "from", "your", "our", "have", "been", "was", "are"}
    sup_toks = {t for t in re.findall(r"[a-z0-9-]+", supports.lower()) if len(t) > 1 and t not in stop}
    if sup_toks:
        best = max(
            sentences,
            key=lambda item: (
                len(sup_toks & set(re.findall(r"[a-z0-9-]+", item[2].lower()))),
                len(item[2]),
            ),
        )
        if len(sup_toks & set(re.findall(r"[a-z0-9-]+", best[2].lower()))) > 0:
            return best[0], best[1]

    for s, e, txt in sentences:
        if len(txt) > 18 and not txt.lower().startswith(("hi", "hello", "dear", "thank you,")):
            return s, e
    return sentences[0][0], sentences[0][1]


def _pick_vendor_field(vendor: dict, explicit_field: str | None, supports: str) -> str:
    if explicit_field:
        mapping = {
            "account": "account",
            "routing": "routing",
            "bank": "bank_name",
            "bank_name": "bank_name",
            "contact": "trusted_contact",
            "trusted_contact": "trusted_contact",
            "alias": "aliases",
            "aliases": "aliases",
            "verified_on": "verified_on",
        }
        return mapping.get(explicit_field, "account")
    low = supports.lower()
    vp = vendor.get("verified_payment") or {}
    acct4 = str(vp.get("account_number", ""))[-4:]
    rout4 = str(vp.get("routing_number", ""))[-4:]
    if (acct4 and acct4 in low) or "account" in low:
        return "account"
    if (rout4 and rout4 in low) or "routing" in low:
        return "routing"
    if "alias" in low or "also known" in low or "name" in low:
        return "aliases"
    if "contact" in low or "call" in low or "phone" in low or (vendor.get("trusted_contact") or "").split(",")[0].lower() in low:
        return "trusted_contact"
    if (vp.get("bank_name") or "").lower() in low or "bank" in low:
        return "bank_name"
    return "account"


@dataclass
class Conversation:
    session: ChatSession
    lock: threading.Lock = field(default_factory=threading.Lock)
    cited_supports: dict[str, str] = field(default_factory=dict)


class DemoService:
    def __init__(self, mode: str = "rehearsal", session_factory=None, bundle: Path | None = None):
        if mode not in ("live", "rehearsal"):
            raise ValueError("Choose live or rehearsal mode.")
        self.mode = mode
        self.bundle = Path(bundle) if bundle is not None else (PROJECT / "data/dev/cafe_01")
        self.sessions: dict[str, Conversation] = {}
        self.lock = threading.Lock()
        self.session_factory = session_factory
        self.token = secrets.token_urlsafe(32)
        self._page_cache: dict[tuple[str, str, int, int], CachedPdfPage] = {}
        self._cache_lock = threading.Lock()
        self._default_stores: tuple[Store | None, Store] | None = None

    def metadata(self):
        return {"mode": self.mode, "business": "Ember & Oat Cafe", "as_of": "2026-09-24",
                "dataset": "Synthetic café records", "token": self.token, "questions": QUESTIONS,
                "configs": [{"id": k, "name": v[0], "description": v[1]} for k, v in CONFIGS.items()]}

    def create(self, config: str) -> str:
        if config not in CONFIGS:
            raise ValueError("Choose a supported configuration.")
        if config in ("C2", "C3") and not (self.bundle / "extracted.sqlite").is_file():
            raise ValueError("Extracted records are missing. Run extraction before using this configuration.")
        if self.session_factory:
            session = self.session_factory(config)
        else:
            # Live credentials are read only by the existing provider client after
            # the user submits their first question. Starting the web page is free.
            session = ChatSession(self.bundle, config, rehearsal_llm())
        with self.lock:
            if len(self.sessions) >= 32:
                raise ValueError("This local server has reached its conversation limit. Restart it to clear sessions.")
            sid = secrets.token_urlsafe(24)
            self.sessions[sid] = Conversation(session)
        return sid

    def discard(self, sid: str):
        with self.lock:
            c = self.sessions.get(sid)
            if c is None:
                return
            if not c.lock.acquire(blocking=False):
                raise ValueError("Wait for the current answer before resetting the conversation.")
            self.sessions.pop(sid, None)
        try:
            for store in (getattr(c.session, "extracted_store", None), getattr(c.session, "gold_store", None)):
                if store is not None:
                    store.conn.close()
        finally:
            c.lock.release()

    def ask(self, sid: str, question: str) -> dict:
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError("Enter a question between 1 and 2,000 characters.")
        with self.lock:
            c = self.sessions.get(sid)
            if c is None:
                raise ValueError("This conversation has expired. Start a new conversation.")
            if not c.lock.acquire(blocking=False):
                raise ValueError("A question is already running in this conversation.")
        try:
            if len(c.session.history) >= 30:
                raise ValueError("Start a new conversation to continue after 30 questions.")
            if self.mode == "live" and not self.session_factory and c.session.llm.model == "scripted":
                from cashbooks.llm.claude import ClaudeLLM
                c.session.llm = ClaudeLLM()
            previous_length = len(c.session.history)
            result = c.session.ask(question.strip())
            if result.response is None:
                # Invalid replies must not silently become conversational evidence.
                del c.session.history[previous_length:]
            else:
                for cit in result.citations:
                    c.cited_supports[cit.evidence_id] = mask_numbers(cit.supports)
            return present_result(result, self.mode)
        finally:
            c.lock.release()

    def _stores_for_session(self, sid: str | None) -> tuple[Store | None, Store, dict[str, str]]:
        if sid:
            with self.lock:
                conv = self.sessions.get(sid)
            if conv is None:
                raise EvidenceNotFoundError("not found in records")
            sess = conv.session
            cfg_store = getattr(getattr(sess, "config", None), "store", None)
            ext = getattr(sess, "extracted_store", None)
            gold = getattr(sess, "gold_store", None)
            if cfg_store is not None or ext is not None or gold is not None:
                return cfg_store or ext, gold or cfg_store or ext, dict(conv.cited_supports)
        with self.lock:
            if self._default_stores is None:
                gold, _ = load_gold(self.bundle)
                ext = None
                xdb = self.bundle / "extracted.sqlite"
                if xdb.is_file():
                    conn = sqlite3.connect(str(xdb), check_same_thread=False)
                    conn.row_factory = sqlite3.Row
                    ext = Store(conn, gold.business_id)
                self._default_stores = (ext, gold)
            ext, gold = self._default_stores
        return ext, gold, {}

    def _safe_bundle_path(self, rel_path: str) -> Path:
        root = self.bundle.resolve()
        candidate = (root / rel_path).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise EvidenceNotFoundError("not found in records")
        return candidate

    def _cached_pdf_page(self, rel_path: str, page_num: int) -> CachedPdfPage:
        pdf_path = self._safe_bundle_path(rel_path)
        key = (str(self.bundle.resolve()), rel_path, page_num, PDF_DPI)
        with self._cache_lock:
            cached = self._page_cache.get(key)
        if cached is not None:
            return cached
        rendered = _render_redacted_base_page(pdf_path, page_num, dpi=PDF_DPI)
        with self._cache_lock:
            existing = self._page_cache.get(key)
            if existing is not None:
                return existing
            self._page_cache[key] = rendered
        return rendered

    def _resolve_pdf_evidence(
        self, eid: str, primary_store: Store | None, fallback_store: Store
    ) -> tuple[str, str, int, CachedPdfPage, tuple[float, float, float, float] | None]:
        stores = [s for s in (primary_store, fallback_store) if s is not None]
        pm = _PAGE_SPAN_RE.fullmatch(eid)
        if pm:
            kind, doc_num, page_str = pm.groups()
            page_num = int(page_str)
            doc_id = f"{kind}_{doc_num}"
            rel_path = None
            for st in stores:
                row = st.conn.execute(
                    "SELECT path FROM documents WHERE business_id = ? AND doc_id = ?",
                    (st.business_id, doc_id),
                ).fetchone()
                if row:
                    rel_path = row["path"]
                    break
            if rel_path is None:
                folder = "invoices" if kind == "inv" else "credits"
                rel_path = f"{folder}/{doc_num}.pdf"
            cached = self._cached_pdf_page(rel_path, page_num)
            label = "Invoice" if kind == "inv" else "Credit note"
            title = f"{label} {doc_num} · page {page_num}"
            return title, rel_path, page_num, cached, None

        fm = _FIELD_SPAN_RE.fullmatch(eid)
        if not fm:
            raise EvidenceNotFoundError("not found in records")
        kind, doc_num, field_name = fm.groups()

        span = None
        doc_path = None
        for st in stores:
            sp = st.span(eid)
            if sp is not None:
                span = sp
                row = st.conn.execute(
                    "SELECT path FROM documents WHERE business_id = ? AND doc_id = ?",
                    (st.business_id, sp.doc_id),
                ).fetchone()
                if row:
                    doc_path = row["path"]
                break

        page_num = span.page if span is not None else 1
        quote_text = span.quote if span is not None else None
        start = span.start if span is not None else None
        end = span.end if span is not None else None

        if span is None:
            folder = "invoices" if kind == "inv" else "credits"
            rel_mf = f"{folder}/{doc_num}.fields.json"
            mf_path = self._safe_bundle_path(rel_mf)
            mf = json.loads(mf_path.read_text(encoding="utf-8"))
            if field_name in mf.get("fields", {}):
                finfo = mf["fields"][field_name]
                quote_text = finfo.get("text")
                page_num = int(finfo.get("page", 1))
                doc_path = f"{folder}/{doc_num}.pdf"
            elif field_name.startswith("line") and field_name[4:].isdigit():
                idx = int(field_name[4:]) - 1
                lines = mf.get("lines", [])
                if 0 <= idx < len(lines):
                    quote_text = lines[idx].get("text")
                    page_num = int(lines[idx].get("page", 1))
                    doc_path = f"{folder}/{doc_num}.pdf"
            else:
                raise EvidenceNotFoundError("not found in records")

        if doc_path is None:
            folder = "invoices" if kind == "inv" else "credits"
            doc_path = f"{folder}/{doc_num}.pdf"

        cached = self._cached_pdf_page(doc_path, page_num)
        box_pt = _locate_span_box(cached, field_name, quote_text, start, end)
        label = "Invoice" if kind == "inv" else "Credit note"
        title = f"{label} {doc_num} · page {page_num} · {_field_human_title(field_name)}"
        return title, doc_path, page_num, cached, box_pt

    def render_evidence_png(self, eid: str, sid: str | None = None) -> bytes:
        if not eid or len(eid) > 128 or ".." in eid or "/" in eid or "\\" in eid or not _VALID_EID.fullmatch(eid):
            raise EvidenceNotFoundError("not found in records")
        primary, fallback, _ = self._stores_for_session(sid)
        _, _, _, cached, box_pt = self._resolve_pdf_evidence(eid, primary, fallback)
        return _render_highlighted_png(cached, box_pt)

    def get_evidence(self, eid: str, sid: str | None = None, supports: str | None = None) -> dict:
        if not eid or len(eid) > 128 or ".." in eid or "/" in eid or "\\" in eid or not _VALID_EID.fullmatch(eid):
            raise EvidenceNotFoundError("not found in records")
        primary, fallback, cited_supports = self._stores_for_session(sid)
        claim = mask_numbers(cited_supports.get(eid) or supports or "")

        if eid.startswith(("span_inv_", "span_cn_")):
            title, _, page_num, cached, box_pt = self._resolve_pdf_evidence(eid, primary, fallback)
            highlight = None
            if box_pt is not None:
                s = cached.scale
                img_w = cached.redacted_image.width
                img_h = cached.redacted_image.height
                highlight = {
                    "x0": round(max(0.0, box_pt[0] * s / img_w), 5),
                    "top": round(max(0.0, box_pt[1] * s / img_h), 5),
                    "x1": round(min(1.0, box_pt[2] * s / img_w), 5),
                    "bottom": round(min(1.0, box_pt[3] * s / img_h), 5),
                    "px_x0": round(box_pt[0] * s, 1),
                    "px_top": round(box_pt[1] * s, 1),
                    "px_x1": round(box_pt[2] * s, 1),
                    "px_bottom": round(box_pt[3] * s, 1),
                }
            return {
                "kind": "pdf_page",
                "evidence_id": eid,
                "title": title,
                "page": page_num,
                "dpi": PDF_DPI,
                "width": cached.redacted_image.width,
                "height": cached.redacted_image.height,
                "highlight": highlight,
                "supports": claim,
            }

        if eid.startswith("txn_"):
            rows = sorted(
                read_bank_csv(self._safe_bundle_path("bank.csv")),
                key=lambda r: (r["posted_on"], r["txn_id"]),
            )
            idx = next((i for i, r in enumerate(rows) if r["txn_id"] == eid), None)
            if idx is None:
                raise EvidenceNotFoundError("not found in records")
            start = max(0, idx - 3)
            end = min(len(rows), start + 7)
            start = max(0, end - 7)
            window = []
            for r in rows[start:end]:
                window.append({
                    "txn_id": r["txn_id"],
                    "posted_on": r["posted_on"].isoformat(),
                    "descriptor": mask_numbers(r["descriptor"]),
                    "amount": f"{r['amount']:.2f}",
                    "currency": r["currency"],
                    "highlighted": r["txn_id"] == eid,
                })
            cited_date = rows[idx]["posted_on"].isoformat()
            return {
                "kind": "bank",
                "evidence_id": eid,
                "title": f"Bank statement · {cited_date} · {eid}",
                "highlighted_id": eid,
                "rows": window,
                "supports": claim,
            }

        mm = _MSG_ID_RE.fullmatch(eid)
        if mm:
            mid = mm.group(1)
            msgs = read_messages(self._safe_bundle_path("messages.jsonl"))
            msg = next((m for m in msgs if m["msg_id"] == mid), None)
            if msg is None:
                raise EvidenceNotFoundError("not found in records")
            masked_body = mask_numbers(msg["body"])
            stored_quote = None
            for st in (primary, fallback):
                if st is not None:
                    sp = st.span(f"span_msg_{mid}") or st.span(eid)
                    if sp is not None:
                        stored_quote = sp.quote
                        break
            h_start, h_end = _sentence_highlight_range(masked_body, stored_quote, claim)
            return {
                "kind": "message",
                "evidence_id": eid,
                "title": f"Vendor message · {mid} · {msg['received_on']}",
                "channel": msg.get("channel", "email"),
                "from": mask_numbers(msg["from"]),
                "received_on": msg["received_on"],
                "subject": mask_numbers(msg.get("subject", "")),
                "body": masked_body,
                "highlight_start": h_start,
                "highlight_end": h_end,
                "supports": claim,
            }

        vm = _VH_ID_RE.fullmatch(eid)
        if vm:
            vid, explicit_field = vm.groups()
            vendors = read_vendor_history(self._safe_bundle_path("vendor_history.json"))
            vendor = next((v for v in vendors if v["vendor_id"] == vid), None)
            if vendor is None:
                raise EvidenceNotFoundError("not found in records")
            vp = vendor.get("verified_payment") or {}
            aliases = [
                f"{a['alias']} ({'verified' if a.get('verified') else 'unverified'})"
                for a in vendor.get("aliases", [])
            ]
            highlighted_field = _pick_vendor_field(vendor, explicit_field, claim)
            return {
                "kind": "vendor",
                "evidence_id": eid,
                "title": f"Trusted vendor record · {vendor['canonical_name']}",
                "highlighted_field": highlighted_field,
                "vendor": {
                    "vendor_id": vendor["vendor_id"],
                    "canonical_name": vendor["canonical_name"],
                    "aliases": aliases,
                    "bank_name": vp.get("bank_name") or "",
                    "account": mask_numbers(str(vp.get("account_number", ""))),
                    "routing": mask_numbers(str(vp.get("routing_number", ""))),
                    "verified_on": vp.get("verified_on") or "",
                    "trusted_contact": mask_numbers(vendor.get("trusted_contact") or ""),
                },
                "supports": claim,
            }

        raise EvidenceNotFoundError("not found in records")


def make_server(port=8765, mode="rehearsal", service=None):
    app = service or DemoService(mode)
    root = PROJECT / "demo/web"
    static = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log questions, model responses, or credentials to stdout.

        def send(self, status, body, content_type="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def local_host(self):
            return self.headers.get("Host", "") in {f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}

        def do_GET(self):
            if not self.local_host():
                return self.send(403, {"error": "Open this demo from localhost."})
            parts = urlsplit(self.path)
            route = parts.path
            if route == "/api/meta":
                return self.send(200, app.metadata())
            if route in ("/api/evidence", "/api/evidence/page"):
                params = parse_qs(parts.query, keep_blank_values=False)
                eid = (params.get("id") or [""])[0]
                sid = (params.get("session") or [None])[0]
                supports = (params.get("supports") or [None])[0]
                try:
                    if route == "/api/evidence/page":
                        png = app.render_evidence_png(eid, sid)
                        return self.send(200, png, "image/png")
                    payload = app.get_evidence(eid, sid, supports)
                    if payload.get("kind") == "pdf_page":
                        q = f"id={quote(eid, safe='')}"
                        if sid:
                            q += f"&session={quote(sid, safe='')}"
                        payload["image_url"] = f"/api/evidence/page?{q}"
                    return self.send(200, payload)
                except EvidenceNotFoundError:
                    return self.send(404, {"error": "not found in records"})
            if route in static:
                file = root / static[route]
                return self.send(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
            self.send(404, {"error": "Page not found."})

        def do_POST(self):
            origin = self.headers.get("Origin")
            allowed = {f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}"}
            if not self.local_host() or (origin and origin not in allowed) or not hmac.compare_digest(self.headers.get("X-CashBooks-Token", ""), app.token):
                return self.send(403, {"error": "Reload this local page before continuing."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    return self.send(413, {"error": "The request is too large or empty."})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected a question or conversation request.")
                route = urlsplit(self.path).path
                if route == "/api/session":
                    sid = app.create(str(body.get("config", "C3")))
                    try:
                        if body.get("previous"):
                            app.discard(str(body["previous"]))
                    except Exception:
                        app.discard(sid)
                        raise
                    return self.send(200, {"session": sid})
                if route == "/api/ask":
                    return self.send(200, app.ask(str(body.get("session", "")), body.get("question")))
                return self.send(404, {"error": "Action not found."})
            except ValueError as exc:
                return self.send(400, {"error": str(exc)})
            except (Exception, SystemExit):
                # The provider may raise SystemExit for billing/authentication
                # failures. Keep the web server alive and do not expose its error.
                return self.send(503, {"error": "The assistant is unavailable. Check the server's model configuration, API access, and credit balance, then try again. Your question was not answered."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description="CashBooks local presentation app")
    parser.add_argument("--mode", choices=["live", "rehearsal"], default="rehearsal")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.port, args.mode)
    print(f"CashBooks Assist: http://127.0.0.1:{server.server_port} ({args.mode} mode)", flush=True)
    print("Live mode uses the Claude API only when you submit a question.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
