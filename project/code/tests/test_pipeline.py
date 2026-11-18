"""Extraction pipeline, retrieval, scoring, the LLM helpers and the configurations,
all offline (reference extractor and scripted model) on the rendered café scenario."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from cashbooks.configs.answer import build_configs
from cashbooks.configs.retrieval import BM25Retriever, build_raw_chunks, build_record_chunks, recall_at_k, tokenize
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.extraction import InvoiceHeaderExtraction
from cashbooks.contracts.response import AssistantResponse
from cashbooks.extract.pipeline import _clean, call_schema, extract_bundle, score_extraction
from cashbooks.extract.reference import ReferenceExtractor
from cashbooks.llm.base import LLMResult, extract_json, simplify_schema
from cashbooks.llm.scripted import ScriptedLLM
from cashbooks.scoring import check_value, doc_level, score_turn
from cashbooks.store.load_gold import load_gold

CAFE = Path(__file__).resolve().parents[2] / "data" / "dev" / "cafe_01"
rendered = pytest.mark.skipif(not (CAFE / "invoices").exists(), reason="render the café bundle first")
AS_OF = date(2026, 9, 24)


# ---------------------------------------------------------------- extraction


@pytest.fixture(scope="module")
def extracted():
    return extract_bundle(CAFE, ReferenceExtractor(CAFE))


@rendered
def test_reference_extraction_reproduces_gold(extracted):
    gold, _ = load_gold(CAFE)
    q = "select bill_id, txn_id, amount_applied from payment_links order by 1, 2"
    assert extracted.store.conn.execute(q).fetchall() == gold.conn.execute(q).fetchall()
    q = "select bill_id, vendor_id, total, stated_due_date, due_date_derived, remit_account_last4 from bills order by 1"
    assert [tuple(r) for r in extracted.store.conn.execute(q)] == [tuple(r) for r in gold.conn.execute(q)]
    report = score_extraction(CAFE, extracted.extracted)
    assert report["accuracy"] == 1.0, report["errors"]
    assert all(c.ok for c in extracted.calls)


@rendered
def test_extracted_store_answers_like_gold(extracted):
    from cashbooks.tools.registry import run_tool
    gold, _ = load_gold(CAFE)
    args = {"vendor": "Northside", "as_of": "2026-09-24"}
    strip = lambda s: {k: v for k, v in json.loads(s).items() if k != "evidence_ids"}
    assert strip(run_tool(extracted.store, "sum_amount_due", args)) == strip(run_tool(gold, "sum_amount_due", args))


class _Fixed:
    model = "fixed"

    def __init__(self, text):
        self.text = text

    def complete(self, system, messages, json_schema=None):
        return LLMResult(text=self.text)


def test_bad_model_output_is_logged_not_raised():
    parsed, log = call_schema(_Fixed("sorry, I can't"), "extract_invoice_header_v1.md", "x", InvoiceHeaderExtraction, "d")
    assert parsed is None and log.error == "invalid_json" and log.raw == "sorry, I can't"
    parsed, log = call_schema(_Fixed('{"vendor_name": 5}'), "extract_invoice_header_v1.md", "x", InvoiceHeaderExtraction, "d")
    assert parsed is None and log.error.startswith("schema_violation")


def test_clean_fills_quote_and_nulls_empty():
    out = _clean({"total": {"value": "$842.00", "source_quote": "", "page": None}, "memo": {"value": "", "source_quote": "x", "page": 1},
                  "items": [{"description": "Cups", "source_quote": None}]})
    assert out["total"] == {"value": "$842.00", "source_quote": "$842.00", "page": 1}
    assert out["memo"] == {"value": None, "source_quote": None, "page": None}
    assert out["items"][0]["source_quote"] == "Cups" and out["items"][0]["page"] == 1


# ---------------------------------------------------------------- retrieval


def test_tokenize_amount_and_id_variants():
    toks = tokenize("Invoice NS-1048 total $1,750.00 due 09/12")
    assert {"ns-1048", "ns", "1048", "1750.00", "1750"} <= set(toks)


@rendered
def test_bm25_finds_invoice_by_number():
    r = BM25Retriever(build_raw_chunks(CAFE))
    top = [c.chunk_id for c in r.search("what is the total on NS-1048", k=3)]
    assert any(doc_level(c) == "inv_NS-1048" for c in top)
    assert recall_at_k(top, ["span_inv_NS-1048_p1"]) == 1.0


@rendered
def test_record_chunks_use_real_evidence_ids(extracted):
    ids = {c.chunk_id for c in build_record_chunks(extracted.store, AS_OF)}
    assert ids <= extracted.store.evidence_ids() | {c for c in ids if c.startswith("vh_")}


# ---------------------------------------------------------------- scoring


def _resp(**kw):
    base = {"answerability": "ANSWER", "answer": "x", "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "span_inv_NS-1062_total", "supports": "total"}]}
    return AssistantResponse.model_validate({**base, **kw})


def test_check_value_formats():
    r = _resp(answer="NS-1062 has $1,073.25 left, due Oct 1, 2026. 12 bags.")
    assert check_value("1073.25 USD", r) and check_value("2026-10-01", r) and check_value("12", r)
    assert not check_value("73", r)  # a bare number must not match inside a longer one
    assert not check_value("1073.20 USD", r)


def test_score_turn_doc_level_and_must_not():
    r = _resp(answer="NS-1062 is next; NS-1070 is later.")
    s = score_turn(r, Answerability.ANSWER, {"bill": "NS-1062"}, ["inv_NS-1062"], ["NS-1070"])
    assert s.evidence_recall == 1.0 and s.must_not_hits == ["NS-1070"] and not s.success
    s = score_turn(r, Answerability.ABSTAIN, {}, [], [])
    assert not s.answerability_ok and not s.success
    assert score_turn(None, Answerability.ANSWER, {}, [], []).parsed is False


# ---------------------------------------------------------------- LLM helpers


def test_simplify_schema_inlines_refs_and_drops_null():
    s = simplify_schema(InvoiceHeaderExtraction.model_json_schema())
    assert "$defs" not in json.dumps(s) and "$ref" not in json.dumps(s)
    total = s["properties"]["total"]
    assert total["type"] == "object" and total["properties"]["value"]["type"] == "string"


def test_extract_json_from_fenced_text():
    assert extract_json('Here:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json("no json here") is None


# ---------------------------------------------------------------- configurations


@rendered
def test_all_configs_run_with_scripted_model(extracted):
    gold, _ = load_gold(CAFE)
    cfgs = build_configs(CAFE, gold, extracted.store, "Ember & Oat Cafe", AS_OF, ["C1", "C2", "C3", "C4"])
    llm = ScriptedLLM(tool_plan={"NS-1048": [("get_bill_status", {"invoice_number": "NS-1048", "as_of": "2026-09-24"})]})
    for name, cfg in cfgs.items():
        out = cfg.answer(llm, [], "Did we pay NS-1048?")
        assert out.result.text and out.known_evidence
        if name in ("C3", "C4"):
            assert out.context and out.context[0]["tool"] == "get_bill_status"
            assert "txn_0193" in out.context[0]["result"]
        else:
            assert len(out.context) == 8


def test_bare_or_null_extracted_fields_are_wrapped():
    fields = list(InvoiceHeaderExtraction.model_fields)
    data = {k: {"value": None, "source_quote": None, "page": None} for k in fields}
    data.update(memo="null", invoice_number="NS-1031")
    parsed, log = call_schema(_Fixed(json.dumps(data)), "extract_invoice_header_v1.md", "x", InvoiceHeaderExtraction, "d")
    assert parsed is not None, log.error
    assert parsed.memo.value is None and parsed.invoice_number.value == "NS-1031"
    assert "memo" in log.notes[0] and "invoice_number" in log.notes[0]


def test_postprocess_unwraps_one_code_fence_only():
    from cashbooks.contracts.postprocess import postprocess
    body = '{"answerability": "ABSTAIN", "answer": "I can\'t tell.", "as_of": "2026-09-24"}'
    pp = postprocess("```json\n" + body + "\n```", set())
    assert pp.response is not None and "unwrapped_code_fence" in pp.issues
    assert postprocess("Sure! " + body, set()).response is None
