"""A reference extractor that answers every extraction call from the bundle's own
ledger and field manifests. No network.

It is a perfect extractor by construction, so running the pipeline with it must
reproduce the gold records. That makes it the offline test of the pipeline code
(quote checks, normalization, vendor resolution, payment linking), separate from
how well a real model reads the documents.
"""

from __future__ import annotations

import json
from pathlib import Path

from cashbooks.llm.base import LLMResult, Message


def _f(text: str | None, page: int = 1) -> dict:
    return {"value": text, "source_quote": text, "page": page if text else None}


class ReferenceExtractor:
    model = "reference"

    def __init__(self, bundle: Path):
        self.ledger = json.loads((bundle / "ledger.json").read_text())
        self.manifests: dict[str, dict] = {}
        self.kind: dict[str, str] = {}
        for sub in ("invoices", "credits"):
            for p in sorted((bundle / sub).glob("*.fields.json")):
                name = p.name.removesuffix(".fields.json")
                self.manifests[name] = json.loads(p.read_text())
                self.kind[name] = sub

    def _doc(self, text: str, sub: str = "invoices") -> str:
        """The document's own number is printed before any number it refers to."""
        hits = [(text.find(k), k) for k in self.manifests if self.kind[k] == sub and k in text]
        return min(hits)[1]

    def complete(self, system: str, messages: list[Message], json_schema: dict | None = None) -> LLMResult:
        text = messages[-1].text
        props = set((json_schema or {}).get("properties", {}))
        if "items" in props:
            out = self._lines(text)
        elif "credit_id" in props:
            out = self._credit(text)
        elif "kind" in props:
            out = self._message(text)
        else:
            out = self._header(text)
        return LLMResult(text=json.dumps(out), input_tokens=len(text) // 4, output_tokens=200, model=self.model)

    def complete_with_tools(self, *a, **k):  # not used for extraction
        raise NotImplementedError

    def _header(self, text: str) -> dict:
        fields = self.manifests[self._doc(text)]["fields"]
        get = lambda k: _f(fields[k]["text"], fields[k].get("page", 1)) if k in fields else _f(None)
        names = ["vendor_name", "invoice_number", "issue_date", "stated_due_date", "currency", "subtotal", "tax",
                 "total", "remit_bank_name", "remit_account", "remit_routing", "reference_or_po"]
        out = {n: get(n) for n in names}
        out["payment_terms_raw"] = get("payment_terms")
        out["memo"] = get("memo")
        return out

    def _lines(self, text: str) -> dict:
        num = self._doc(text)
        inv = next(i for i in self.ledger["invoices"] if i["invoice_number"] == num)
        printed = self.manifests[num].get("lines", [])
        items = []
        for i, ln in enumerate(inv["lines"]):
            src = printed[i] if i < len(printed) else {"text": ln["description"], "page": 1}
            items.append({"description": ln["description"], "quantity": ln.get("quantity"), "unit": ln.get("unit"),
                          "unit_price": ln.get("unit_price"), "line_total": ln.get("line_total"),
                          "source_quote": src["text"], "page": src.get("page", 1)})
        return {"items": items}

    def _credit(self, text: str) -> dict:
        fields = self.manifests[self._doc(text, "credits")]["fields"]
        get = lambda k: _f(fields[k]["text"], fields[k].get("page", 1)) if k in fields else _f(None)
        return {"credit_id": get("credit_id"), "invoice_ref": get("invoice_ref"), "amount": get("total"),
                "issue_date": get("issue_date")}

    def _message(self, text: str) -> dict:
        m = next(m for m in self.ledger["messages"] if m["body"] in text)
        return {"kind": m["kind"], "invoice_refs": m.get("invoice_refs", []), "claimed_amount": _f(None),
                "claimed_date": _f(None), "new_remit_bank_name": _f(None), "new_remit_account": _f(None),
                "new_remit_routing": _f(None), "summary_quote": m["body"].split(".")[0]}
