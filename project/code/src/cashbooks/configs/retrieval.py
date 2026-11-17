"""BM25 retrieval for C1 (raw document chunks) and C2 (serialized typed records).

Both use the same tokenizer, the same BM25 parameters and the same k, so the
C1-vs-C2 gap measures representation alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from cashbooks.ingest.bank_csv import read_bank_csv
from cashbooks.ingest.bundle import read_messages, read_vendor_history
from cashbooks.ingest.pdf_text import page_texts
from cashbooks.normalize.fingerprint import mask_digits
from cashbooks.store.db import Store
from cashbooks.tools.status import compute_state

_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-/,][a-z0-9]+)*")
MAX_WORDS = 300


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    text: str


def tokenize(text: str) -> list[str]:
    """Lowercase tokens that keep amounts, dates and invoice numbers whole.

    '$1,118.25' gives '1,118.25' and '1118.25'; '842.00' also gives '842';
    'NS-1048' gives 'ns-1048', 'ns' and '1048'.
    """
    out: list[str] = []
    for t in _TOKEN.findall(text.lower()):
        out.append(t)
        if "," in t:
            out.append(t.replace(",", ""))
        if "-" in t or "/" in t:
            out.extend(p for p in re.split(r"[-/]", t) if p)
        plain = t.replace(",", "")
        if re.fullmatch(r"\d+\.00", plain):
            out.append(plain[:-3])  # "842.00" also matches a query for "$842"
    return out


def _windows(words: list[str]) -> list[str]:
    return [" ".join(words[i:i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS)]


# ---------------------------------------------------------------- C1: raw chunks


def build_raw_chunks(bundle: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for folder, prefix, label in (("invoices", "inv", "invoice"), ("credits", "cn", "credit note")):
        for pdf in sorted((bundle / folder).glob("*.pdf")):
            for pno, text in enumerate(page_texts(pdf), start=1):
                parts = _windows(text.split()) if len(text.split()) > MAX_WORDS else [text]
                for wi, part in enumerate(parts, start=1):
                    suffix = f"_w{wi}" if len(parts) > 1 else ""
                    chunks.append(Chunk(f"span_{prefix}_{pdf.stem}_p{pno}{suffix}",
                                        f"{label} {pdf.stem}, page {pno}", part))
    for m in read_messages(bundle / "messages.jsonl"):
        body = f"From: {m['from']}\nDate: {m['received_on']}\nSubject: {m.get('subject', '')}\n\n{m['body']}"
        chunks.append(Chunk(f"span_msg_{m['msg_id']}", f"{m['channel']} from {m['from']}", body))
    for r in read_bank_csv(bundle / "bank.csv"):
        chunks.append(Chunk(r["txn_id"], f"bank statement row {r['posted_on']}",
                            f"{r['posted_on']} | {r['descriptor']} | {r['amount']:.2f} {r['currency']} | {r['txn_id']}"))
    for v in read_vendor_history(bundle / "vendor_history.json"):
        vp = v.get("verified_payment") or {}
        aliases = ", ".join(f"{a['alias']} ({'verified' if a.get('verified') else 'unverified'})"
                            for a in v.get("aliases", [])) or "none"
        text = (f"Trusted vendor record: {v['canonical_name']}. Aliases: {aliases}. "
                f"Verified payment details: {vp.get('bank_name')}, account ending {str(vp.get('account_number', ''))[-4:]}, "
                f"routing ending {str(vp.get('routing_number', ''))[-4:]}, verified on {vp.get('verified_on')}. "
                f"Contact on file: {v.get('trusted_contact')}.")
        chunks.append(Chunk(f"vh_{v['vendor_id']}", "owner's trusted vendor record", text))
    return chunks


# ---------------------------------------------------------------- C2: serialized records


def build_record_chunks(store: Store, as_of) -> list[Chunk]:
    """One line of typed fields per stored record, cited by a real evidence ID."""
    chunks: list[Chunk] = []
    for b in store.bills():
        st = compute_state(store, b, as_of)
        lines = "; ".join(f"{l.description} qty={l.quantity} {l.unit or ''} unit_price={l.unit_price} line_total={l.line_total}"
                          for l in store.lines(b.bill_id))
        cid = b.field_evidence.get("total") or b.field_evidence.get("invoice_number") or f"span_{b.doc_id}_total"
        text = (f"BILL invoice_number={b.invoice_number} vendor={store.vendor_name(b.vendor_id)} "
                f"printed_vendor_name={b.printed_vendor_name} issue_date={b.issue_date} terms={b.payment_terms_raw} "
                f"stated_due_date={b.stated_due_date} derived_due_date={b.due_date_derived} currency={b.currency} "
                f"subtotal={b.subtotal} tax={b.tax} total={b.total} "
                f"remit_bank={b.remit_bank_name} remit_account_last4={b.remit_account_last4} | lines: {lines}")
        chunks.append(Chunk(cid, f"bill record {b.invoice_number}", text))
    for t in store.txns():
        chunks.append(Chunk(t.txn_id, f"bank record {t.posted_on}",
                            f"BANK txn_id={t.txn_id} posted_on={t.posted_on} amount={t.amount} {t.currency} descriptor={t.descriptor}"))
    for b in store.bills():
        for c in store.credits(b.bill_id):
            chunks.append(Chunk(c.evidence_id, f"credit record {c.credit_id}",
                                f"CREDIT credit_id={c.credit_id} invoice_number={b.invoice_number} amount={c.amount} issued_on={c.issued_on}"))
    for cl in store.claims():
        sp = store.span(cl.evidence_id)
        chunks.append(Chunk(cl.evidence_id, f"message record {cl.doc_id}",
                            f"MESSAGE kind={cl.kind} invoice_refs={','.join(cl.invoice_refs)} "
                            f"new_account_last4={cl.new_account_last4} text={mask_digits(sp.quote) if sp else ''}"))
    for v in store.vendors():
        fps = store.fingerprints(v.vendor_id)
        aliases = ",".join(a.alias for a in store.aliases() if a.vendor_id == v.vendor_id and a.verified)
        if fps:
            fp = fps[0]
            chunks.append(Chunk(fp.evidence_id, "trusted vendor record",
                                f"VENDOR name={v.canonical_name} verified_aliases={aliases} bank={fp.bank_name} "
                                f"account_last4={fp.account_last4} routing_last4={fp.routing_last4} "
                                f"verified_on={fp.verified_on} contact={fp.trusted_contact}"))
    return chunks


# ---------------------------------------------------------------- retriever


class BM25Retriever:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c.source + " " + c.text) for c in chunks])

    def search(self, query: str, k: int = 8) -> list[Chunk]:
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(self.chunks)), key=lambda i: (-scores[i], self.chunks[i].chunk_id))
        return [self.chunks[i] for i in order[:k]]

    def search_conversation(self, user_turns: list[str], k: int = 8) -> list[Chunk]:
        return self.search(" ".join(user_turns[-3:]), k)


def render_context(chunks: list[Chunk]) -> str:
    return "\n\n".join(f"[{c.chunk_id}] {c.source}\n{c.text}" for c in chunks)


def recall_at_k(retrieved_ids: list[str], gold_ids: list[str]) -> float | None:
    if not gold_ids:
        return None
    return sum(1 for g in gold_ids if g in retrieved_ids) / len(gold_ids)
