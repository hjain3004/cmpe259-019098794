"""Tests for the plumbing_01 bundle, tool enhancements (Q23-Q28), check_gold,
and bundle-level turn text overrides."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from cashbooks.contracts.evaluation import QuerySuite
from cashbooks.demo.session import ChatSession, resolve_turn_texts
from cashbooks.extract.pipeline import extract_bundle, score_extraction
from cashbooks.extract.reference import ReferenceExtractor
from cashbooks.llm.scripted import ScriptedLLM
from cashbooks.scoring import doc_level
from cashbooks.store.load_gold import gold_links, load_gold
from cashbooks.tools.registry import run_tool

PROJECT = Path(__file__).resolve().parents[2]
CAFE = PROJECT / "data" / "dev" / "cafe_01"
PLUMBING = PROJECT / "data" / "dev" / "plumbing_01"
AS_OF = date(2026, 9, 24)


def _load_check_gold():
    path = PROJECT / "data" / "generator" / "check_gold.py"
    spec = importlib.util.spec_from_file_location("check_gold", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_gold"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def plumbing_gold():
    store, report = load_gold(PLUMBING)
    assert report.ungrounded == [], report.ungrounded
    return store


@pytest.fixture(scope="module")
def plumbing_extracted():
    return extract_bundle(PLUMBING, ReferenceExtractor(PLUMBING))


def call(store, name: str, **args) -> dict:
    return json.loads(run_tool(store, name, args))


def test_check_gold_passes_on_both_bundles():
    cg = _load_check_gold()
    assert cg.check_bundle(CAFE) == []
    assert cg.check_bundle(PLUMBING) == []


def test_plumbing_reference_extraction_matches_gold(plumbing_gold, plumbing_extracted):
    report = score_extraction(PLUMBING, plumbing_extracted.extracted)
    assert report["accuracy"] == 1.0, report["errors"]
    assert all(c.ok for c in plumbing_extracted.calls)

    q = "select bill_id, txn_id, amount_applied, status, reasons from payment_links order by 1, 2"
    assert [tuple(r) for r in plumbing_extracted.store.conn.execute(q)] == [
        tuple(r) for r in plumbing_gold.conn.execute(q)
    ]
    ledger_pairs = {(l.bill_id, l.txn_id) for l in gold_links(PLUMBING)}
    assert {(r[0], r[1]) for r in plumbing_gold.conn.execute("select bill_id, txn_id from payment_links")} == ledger_pairs


def test_turn_text_override_resolution():
    suite = QuerySuite.model_validate(yaml.safe_load((PROJECT / "evaluation" / "queries.yaml").read_text()))
    convs = {c.id: c for c in suite.conversations}
    plumbing_gold_yaml = yaml.safe_load((PLUMBING / "gold.yaml").read_text())
    cafe_gold_yaml = yaml.safe_load((CAFE / "gold.yaml").read_text())

    # Café has no overrides, so texts match queries.yaml verbatim
    for qid in cafe_gold_yaml:
        if qid.startswith("Q"):
            assert resolve_turn_texts(convs[qid], cafe_gold_yaml[qid]) == [t.text for t in convs[qid].turns]

    # Plumbing overrides vendor/invoice names where specified and keeps original wording otherwise
    assert resolve_turn_texts(convs["Q04"], plumbing_gold_yaml["Q04"]) == ["Did I already pay invoice CP-418?"]
    assert resolve_turn_texts(convs["Q18"], plumbing_gold_yaml["Q18"]) == [
        "Is this safe to pay?",
        "The Summit Brass one from September.",
        "Why?",
    ]
    assert resolve_turn_texts(convs["Q21"], plumbing_gold_yaml["Q21"]) == [
        "List my Crestline bills from July and August, oldest first.",
        "Was the second invoice paid?",
        "And the first?",
    ]
    assert resolve_turn_texts(convs["Q22"], plumbing_gold_yaml["Q22"]) == [t.text for t in convs["Q22"].turns]
    assert resolve_turn_texts(convs["Q23"], plumbing_gold_yaml["Q23"]) == ["When is CT-88 due?"]

    sess = ChatSession(PLUMBING, "C4", ScriptedLLM())
    assert sess.turn_texts("Q04") == ["Did I already pay invoice CP-418?"]
    assert sess.turn_texts("Q22")[1] == "Compared with the previous invoice?"


def test_status_value_matching_synonyms_and_negations():
    from cashbooks.contracts.response import AssistantResponse
    from cashbooks.scoring import check_value

    def _r(ans: str) -> AssistantResponse:
        return AssistantResponse.model_validate({
            "answerability": "ANSWER",
            "answer": ans,
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "span_inv_CP-401_total", "supports": "status"}],
        })

    # "unpaid" vs "paid"
    assert check_value("unpaid", _r("Invoice CP-401 is unpaid.")) is True
    assert check_value("paid", _r("Invoice CP-401 is unpaid.")) is False
    assert check_value("paid", _r("Invoice CP-401 is not paid.")) is False
    assert check_value("unpaid", _r("Invoice CP-401 is not paid.")) is True

    # "has not been paid" and "open" / "outstanding"
    assert check_value("unpaid", _r("Invoice CP-401 has not been paid.")) is True
    assert check_value("paid", _r("Invoice CP-401 has not been paid.")) is False
    assert check_value("unpaid", _r("Invoice CP-401 is still open and outstanding.")) is True

    # "partially paid"
    assert check_value("partially paid", _r("Invoice PL-314 is partially paid.")) is True
    assert check_value("partially paid", _r("Invoice PL-314 is partly paid.")) is True
    assert check_value("paid", _r("Invoice PL-314 is partially paid.")) is False
    assert check_value("paid", _r("Invoice PL-314 is partly paid.")) is False

    # Positive "paid" / "paid in full" / "settled"
    assert check_value("paid", _r("Invoice CP-418 has been paid in full.")) is True
    assert check_value("paid", _r("Invoice CP-418 is settled.")) is True
    assert check_value("unpaid", _r("Invoice CP-418 is paid in full.")) is False


def test_rescore_handles_dict_shaped_gold_entry(tmp_path, plumbing_extracted, monkeypatch):
    from cashbooks.contracts.common import Answerability
    from cashbooks.contracts.evaluation import LogRow
    from cashbooks.scoring import write_log, write_run_outputs
    sys.path.insert(0, str(PROJECT / "evaluation"))
    import rescore

    xdb = PLUMBING / "extracted.sqlite"
    if not xdb.exists():
        extract_bundle(PLUMBING, ReferenceExtractor(PLUMBING), xdb)

    run_dir = tmp_path / "run_q21"
    run_dir.mkdir()
    setup_resp = json.dumps({
        "answerability": "ANSWER",
        "answer": "1. CP-401, 2. CP-418, 3. CT-88.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_CP-401_total", "supports": "list"}],
    })
    t1_resp = json.dumps({
        "answerability": "ANSWER",
        "answer": "Yes, the second invoice CP-418 is paid.",
        "as_of": "2026-09-24",
        "evidence": [
            {"evidence_id": "span_inv_CP-418_total", "supports": "invoice"},
            {"evidence_id": "txn_0326", "supports": "payment"},
        ],
    })
    t2_resp = json.dumps({
        "answerability": "ANSWER",
        "answer": "No, the first invoice CP-401 is unpaid.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_CP-401_total", "supports": "invoice"}],
    })
    rows = [
        LogRow(
            query_id="Q21", turn_index=0, turn_text="List my Crestline bills from July and August.",
            scenario="plumbing_01", business_type="plumbing", split="dev", configuration="C4",
            model_version="scripted", prompt_version="answer_system_v1", code_commit="abc",
            context=[], raw_response=setup_resp, parsed_ok=True, expected=Answerability.ANSWER,
            success=None, scores={"setup_turn": True}, notes="setup turn, not scored",
            latency_ms=10, input_tokens=100, output_tokens=20,
        ),
        LogRow(
            query_id="Q21", turn_index=1, turn_text="Was the second invoice paid?",
            scenario="plumbing_01", business_type="plumbing", split="dev", configuration="C4",
            model_version="scripted", prompt_version="answer_system_v1", code_commit="abc",
            context=[], raw_response=t1_resp, parsed_ok=True, expected=Answerability.ANSWER,
            success=True, scores={"parsed": True, "answerability_ok": True, "values": {"bill": True, "status": True},
                                  "evidence_recall": 1.0, "evidence_precision": 1.0, "must_not_hits": [], "success": True},
            latency_ms=10, input_tokens=100, output_tokens=20,
        ),
        LogRow(
            query_id="Q21", turn_index=2, turn_text="And the first?",
            scenario="plumbing_01", business_type="plumbing", split="dev", configuration="C4",
            model_version="scripted", prompt_version="answer_system_v1", code_commit="abc",
            context=[], raw_response=t2_resp, parsed_ok=True, expected=Answerability.ANSWER,
            success=True, scores={"parsed": True, "answerability_ok": True, "values": {"bill": True, "status": True},
                                  "evidence_recall": 1.0, "evidence_precision": 1.0, "must_not_hits": [], "success": True},
            latency_ms=10, input_tokens=100, output_tokens=20,
        ),
    ]
    write_log(rows, run_dir / "log.jsonl")
    write_run_outputs([r for r in rows if r.success is not None], run_dir, "run_q21", "scripted", "abc", str(PLUMBING), ["Q21"], 2, "answer_system_v1")

    monkeypatch.setattr(sys, "argv", ["rescore.py", str(run_dir), str(PLUMBING)])
    assert rescore.main() == 0
    rescored_summary = json.loads((run_dir / "rescored" / "summary.json").read_text())
    assert rescored_summary["configs"]["C4"]["successes"] == 2
    assert rescored_summary["per_conversation"]["C4"]["Q21"] is True


def test_tool_enhancements_line_items_po_and_printed_vendor(plumbing_gold):
    # Q23: CT-88 due date conflict
    ct88 = call(plumbing_gold, "get_bill_status", invoice_number="CT-88", as_of="2026-09-24")
    assert ct88["stated_due_date"] == "2026-09-04"
    assert ct88["derived_due_date"] == "2026-09-19"
    assert ct88["due_date_conflict"] is True

    # Q24: SUM-44 line items sum mismatch ($1,185.00 vs $1,240.00 stated total)
    sum44 = call(plumbing_gold, "get_bill_status", invoice_number="SUM-44", as_of="2026-09-24")
    assert len(sum44["line_items"]) == 2
    assert sum44["line_items_sum"] == {"amount": "1185.00", "currency": "USD"}
    assert sum44["bill"]["total"] == {"amount": "1240.00", "currency": "USD"}
    assert sum44["line_items_match_subtotal"] is True
    assert sum44["total_matches_subtotal_plus_tax"] is False

    # Q26: ML-090 and ML-90 duplicates share vendor, date, total, line items, and reference_or_po
    ml090 = call(plumbing_gold, "get_bill_status", invoice_number="ML-090", as_of="2026-09-24")
    ml90 = call(plumbing_gold, "get_bill_status", invoice_number="ML-90", as_of="2026-09-24")
    assert ml090["bill"]["total"] == ml90["bill"]["total"] == {"amount": "378.00", "currency": "USD"}
    assert ml090["bill"]["issue_date"] == ml90["bill"]["issue_date"] == "2026-09-11"
    assert ml090["reference_or_po"] == ml90["reference_or_po"] == "PO-7160"
    assert [i["description"] for i in ml090["line_items"]] == [i["description"] for i in ml90["line_items"]]
    assert "span_inv_ML-090_reference_or_po" in ml090["bill"]["evidence_ids"]

    # Q27: printed_vendor_name exposed in list_open_bills for legal-name change
    crestline_bills = call(plumbing_gold, "list_open_bills", as_of="2026-09-24", vendor="Crestline", include_settled=True)["bills"]
    by_num = {b["invoice_number"]: b["printed_vendor_name"] for b in crestline_bills}
    assert by_num["CP-401"] == "Crestline Pipe & Supply"
    assert by_num["CP-418"] == "Crestline Pipe & Supply"
    assert by_num["CT-88"] == "Crestline Pipe & Supply"
    assert by_num["PL-314"] == "Crestline Flow Systems LLC"
    assert by_num["CP-445"] == "Crestline Flow Systems LLC"


def test_plumbing_tools_support_all_30_gold_conversations(plumbing_gold):
    gold = yaml.safe_load((PLUMBING / "gold.yaml").read_text())
    qids = sorted(k for k in gold if k.startswith("Q"))
    assert qids == [f"Q{i:02d}" for i in range(1, 31)]

    # Q01: bills due in the next seven days (2026-09-24..2026-10-01)
    r01 = call(plumbing_gold, "list_open_bills", as_of="2026-09-24", due_before="2026-10-01")
    upcoming01 = [b for b in r01["bills"] if b["due_date"] >= "2026-09-24"]
    assert [b["invoice_number"] for b in upcoming01] == ["MV-309", "PL-314"]
    pl314_01 = next(b for b in upcoming01 if b["invoice_number"] == "PL-314")
    assert pl314_01["remaining"] == {"amount": "760.00", "currency": "USD"}

    # Q02 & Q19: owed to Crestline as of Sep 30 / Sep 24, and overdue only
    r02 = call(plumbing_gold, "sum_amount_due", as_of="2026-09-30", vendor="Crestline")
    assert r02["totals"] == [{"amount": "2275.20", "currency": "USD"}]
    r19_over = call(plumbing_gold, "sum_amount_due", as_of="2026-09-24", vendor="Crestline", overdue_only=True)
    assert r19_over["totals"] == [{"amount": "1060.20", "currency": "USD"}]

    # Q03: overdue invoices as of 2026-09-24
    r03 = call(plumbing_gold, "list_open_bills", as_of="2026-09-24")
    overdue03 = [b["invoice_number"] for b in r03["bills"] if b["overdue"]]
    assert overdue03 == ["CP-401", "CT-88", "SUM-44"]

    # Q04 & Q08 & Q09: CP-418 paid by txn_0326 ($788.40 on 2026-09-12), subtotal 729.00 + tax 59.40
    r04 = call(plumbing_gold, "get_bill_status", invoice_number="CP-418", as_of="2026-09-24")
    assert r04["bill"]["state"] == "paid"
    assert r04["subtotal"] == {"amount": "729.00", "currency": "USD"}
    assert r04["tax"] == {"amount": "59.40", "currency": "USD"}
    assert [p["txn_id"] for p in r04["payments"]] == ["txn_0326"]
    r09 = call(plumbing_gold, "match_payments", amount="788.40", posted_on="2026-09-12")
    assert r09["outcome"] == "confirmed" and r09["candidates"][0]["invoice_number"] == "CP-418"

    # Q05 & Q06: MV-309 derived due date 2026-09-25, partial payment $250 (txn_0322) leaving $330.00
    r05 = call(plumbing_gold, "get_bill_status", invoice_number="MV-309", as_of="2026-09-24")
    assert r05["stated_due_date"] is None and r05["derived_due_date"] == "2026-09-25"
    assert r05["remaining_if_candidates_apply"] == {"amount": "330.00", "currency": "USD"}
    assert [p["txn_id"] for p in r05["possible_payments"]] == ["txn_0322"]
    assert r05["conflicting_claims"] == ["span_msg_m03"]

    # Q07, Q12, Q13, Q18, Q20, Q22: SB-522 payment details changed (8841 vs 0345, Marcus Bell), memo note, total 2110 vs SB-510 640
    r12 = call(plumbing_gold, "compare_vendor_payment_details", invoice_number="SB-522")
    assert r12["outcome"] == "changed"
    assert r12["on_document"]["account_last4"] == "8841"
    assert r12["on_file"]["account_last4"] == "0345"
    assert "Marcus Bell" in r12["trusted_contact"]
    r13 = call(plumbing_gold, "get_bill_status", invoice_number="SB-522", as_of="2026-09-24")
    assert r13["bill"]["total"] == {"amount": "2110.00", "currency": "USD"}
    assert r13["has_note_outside_remit_fields"] is True
    assert "replaces SB-510" in " ".join(r13["memo"].split())
    r_sb510 = call(plumbing_gold, "get_bill_status", invoice_number="SB-510", as_of="2026-09-24")
    assert r_sb510["bill"]["total"] == {"amount": "640.00", "currency": "USD"}

    # Q10 & Q17: MV-301 paid twice (txn_0304 confirmed, txn_0308 candidate duplicate)
    r10 = call(plumbing_gold, "match_payments", invoice_number="MV-301")
    assert [c["txn_id"] for c in r10["candidates"]] == ["txn_0304", "txn_0308"]

    # Q11 & Q27: Crestline verified alias in vh_v_crestline
    r11 = call(plumbing_gold, "get_source_evidence", evidence_ids=["vh_v_crestline"])
    assert "Crestline Flow Systems LLC" in r11["quotes"][0]["quote"]

    # Q14 & Q15 & Q29: August copper pipe purchases
    r14 = call(plumbing_gold, "summarize_purchases", item="copper pipe", date_from="2026-08-01", date_to="2026-08-31")
    assert r14["spend"] == [{"amount": "691.00", "currency": "USD"}]
    r15 = call(plumbing_gold, "summarize_purchases", item="Type L copper pipe 3/4", date_from="2026-08-01", date_to="2026-08-31")
    assert r15["quantities"] == [{"unit": "length", "quantity": "15.00"}]

    # Q16 & Q21: Crestline open bills & July/August bills
    r16 = call(plumbing_gold, "list_open_bills", as_of="2026-09-24", vendor="Crestline")
    assert [b["invoice_number"] for b in r16["bills"]] == ["CP-401", "CT-88", "PL-314", "CP-445"]

    # Q25: PL-314 total 1250 - 400 payment (txn_0329) - 90 credit (CN-0812) = 760.00
    r25 = call(plumbing_gold, "get_bill_status", invoice_number="PL-314", as_of="2026-09-24")
    assert r25["bill"]["total"] == {"amount": "1250.00", "currency": "USD"}
    assert r25["bill"]["remaining"] == {"amount": "760.00", "currency": "USD"}
    assert [p["txn_id"] for p in r25["payments"]] == ["txn_0329"]
    assert r25["credits"] == [{"amount": "90.00", "currency": "USD"}]
    assert {"inv_PL-314", "txn_0329", "cn_CN-0812"} <= {doc_level(e) for e in r25["bill"]["evidence_ids"]}

    # Q28: open bills in USD and EUR
    r28 = call(plumbing_gold, "sum_amount_due", as_of="2026-09-24")
    assert r28["totals"] == [
        {"amount": "720.00", "currency": "EUR"},
        {"amount": "6961.20", "currency": "USD"},
    ]
    assert r28["totals_if_candidates_apply"] == [
        {"amount": "720.00", "currency": "EUR"},
        {"amount": "6711.20", "currency": "USD"},
    ]

    # Q30: unmatched $1,750 debit on 2026-09-18 (txn_0333)
    r30 = call(plumbing_gold, "match_payments", amount="1750")
    assert r30["outcome"] == "no_candidates" and "txn_0333" in r30["why_undecided"]
