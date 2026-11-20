"""Unit tests for course-lecture evaluation metrics (Items 1-4) on small hand-made inputs."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow
from cashbooks.contracts.records import Bill, BillLine, Document, DocumentKind, Vendor
from cashbooks.store.db import Store, connect, insert

PROJECT = Path(__file__).resolve().parents[2]


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _mk_row(
    cfg: str,
    qid: str,
    ti: int,
    expected: Answerability,
    pred: str | None,
    parsed_ok: bool = True,
    er: float | None = None,
    ep: float | None = None,
    chunks: list[str] | None = None,
) -> LogRow:
    raw = json.dumps({"answerability": pred or "ANSWER", "evidence": []}) if parsed_ok else "not json"
    return LogRow(
        query_id=qid,
        turn_index=ti,
        turn_text=f"Q {qid} t{ti}",
        scenario="mini",
        business_type="cafe",
        split="dev",
        configuration=cfg,
        model_version="m",
        prompt_version="v2",
        code_commit="c",
        context=[{"chunk_id": c, "source": "s"} for c in (chunks or [])],
        raw_response=raw,
        parsed_ok=parsed_ok,
        expected=expected,
        success=True,
        scores={"evidence_recall": er, "evidence_precision": ep},
        notes="",
        latency_ms=10,
        input_tokens=10,
        output_tokens=10,
    )


def test_item1_classification_2x2_confusion_matrix_and_unparsed():
    lm = _load_mod("lecture_metrics", PROJECT / "evaluation" / "lecture_metrics.py")

    # 2x2 hand-made case: 4 expected ANSWER, 2 expected WARN; 1 unparsed WARN
    #   ANSWER: 3 -> ANSWER, 1 -> WARN (TP=3, FN=1, FP=0 => P=1.0, R=0.75, F1=6/7)
    #   WARN:   1 -> WARN,   1 -> UNPARSED (TP=1, FN=1, FP=1 => P=0.5, R=0.5, F1=0.5)
    #   Accuracy = 4/6; Majority baseline = ANSWER (4/6); Macro-F1 = (6/7 + 0.5) / 2
    rows = [
        _mk_row("C0", "Q01", 0, Answerability.ANSWER, "ANSWER"),
        _mk_row("C0", "Q02", 0, Answerability.ANSWER, "ANSWER"),
        _mk_row("C0", "Q03", 0, Answerability.ANSWER, "ANSWER"),
        _mk_row("C0", "Q04", 0, Answerability.ANSWER, "WARN"),
        _mk_row("C0", "Q05", 0, Answerability.WARN, "WARN"),
        _mk_row("C0", "Q06", 0, Answerability.WARN, None, parsed_ok=False),
    ]
    res = lm.evaluate_reply_classification(rows)
    assert res["majority_baseline"]["class"] == "ANSWER"
    assert res["majority_baseline"]["accuracy"] == pytest.approx(4 / 6)

    c0 = res["configs"]["C0"]
    assert c0["accuracy"] == pytest.approx(4 / 6)
    assert c0["delta_vs_majority"] == pytest.approx(0.0)
    assert c0["unparsed"] == 1
    assert c0["confusion_matrix"]["ANSWER"]["ANSWER"] == 3
    assert c0["confusion_matrix"]["ANSWER"]["WARN"] == 1
    assert c0["confusion_matrix"]["WARN"]["WARN"] == 1
    assert c0["confusion_matrix"]["WARN"]["UNPARSED"] == 1

    assert c0["per_class"]["ANSWER"]["precision"] == pytest.approx(1.0)
    assert c0["per_class"]["ANSWER"]["recall"] == pytest.approx(0.75)
    assert c0["per_class"]["ANSWER"]["f1"] == pytest.approx(6 / 7)
    assert c0["per_class"]["WARN"]["precision"] == pytest.approx(0.5)
    assert c0["per_class"]["WARN"]["recall"] == pytest.approx(0.5)
    assert c0["per_class"]["WARN"]["f1"] == pytest.approx(0.5)
    assert c0["macro_f1"] == pytest.approx(((6 / 7) + 0.5) / 2)


def test_item2_retrieval_at_rank_precision_recall_and_mrr():
    rd = _load_mod("retrieval_diagnosis", PROJECT / "evaluation" / "retrieval_diagnosis.py")

    turns = [
        {
            "configuration": "C1",
            "ranked_docs": ["inv_0", "inv_1", "inv_2", "inv_3", "inv_4", "inv_5", "inv_6", "inv_7"],
            "gold_evidence": ["inv_1", "inv_4"],
        },
        {
            "configuration": "C2",
            "ranked_docs": ["inv_1", "inv_4", "inv_2", "inv_3", "inv_5", "inv_6", "inv_7", "inv_8"],
            "gold_evidence": ["inv_1", "inv_4"],
        },
    ]
    st = rd.compute_retrieval_at_rank(turns)

    # C1: gold at ranks 2 and 5 -> MRR=0.5; P@1=0, P@3=1/3, P@5=2/5, P@8=0.25; R@1=0, R@3=0.5, R@5=1, R@8=1
    assert st["C1"]["mrr"] == pytest.approx(0.5)
    assert st["C1"]["precision_at_k"] == {1: pytest.approx(0.0), 3: pytest.approx(1 / 3), 5: pytest.approx(0.4), 8: pytest.approx(0.25)}
    assert st["C1"]["recall_at_k"] == {1: pytest.approx(0.0), 3: pytest.approx(0.5), 5: pytest.approx(1.0), 8: pytest.approx(1.0)}

    # C2: gold at ranks 1 and 2 -> MRR=1.0; P@1=1, P@3=2/3, P@5=0.4, P@8=0.25; R@1=0.5, R@3=1, R@5=1, R@8=1
    assert st["C2"]["mrr"] == pytest.approx(1.0)
    assert st["C2"]["precision_at_k"][1] == pytest.approx(1.0)
    assert st["C2"]["precision_at_k"][3] == pytest.approx(2 / 3)
    assert st["C2"]["recall_at_k"][1] == pytest.approx(0.5)
    assert st["C2"]["recall_at_k"][3] == pytest.approx(1.0)


def test_item3_ner_extraction_partial_match_and_line_items(tmp_path: Path):
    em = _load_mod("extraction_metrics", PROJECT / "evaluation" / "extraction_metrics.py")

    # Partial match on vendor string -> 1 FP and 1 FN (P=0, R=0, F1=0)
    assert em.compare_entity_unit(em._norm_text("Northside Supplies LLC"), em._norm_text("Northside Supplies")) == (0, 1, 1)
    assert em.compare_entity_unit(em._norm_text("Northside Supplies"), em._norm_text("NORTHSIDE SUPPLIES")) == (1, 0, 0)
    assert em.compare_entity_unit("100.00", None) == (0, 0, 1)

    # Line item partial mismatch: line1 matches; line2 wrong line_total -> 1 TP, 1 FP, 1 FN
    g_lines = [
        ("cups", Decimal("2.00"), Decimal("5.00"), Decimal("10.00")),
        ("lids", Decimal("1.00"), Decimal("3.00"), Decimal("3.00")),
    ]
    p_lines = [
        ("cups", Decimal("2.00"), Decimal("5.00"), Decimal("10.00")),
        ("lids", Decimal("1.00"), Decimal("3.00"), Decimal("9.00")),
    ]
    assert em.compare_line_items(g_lines, p_lines) == (1, 1, 1)

    # Store-to-store end-to-end check on 1 synthetic invoice
    g_conn, e_conn = connect(), connect()
    for conn in (g_conn, e_conn):
        insert(conn, [
            Vendor(business_id="b1", vendor_id="v1", canonical_name="Acme Co"),
            Document(business_id="b1", doc_id="inv_1", kind=DocumentKind.INVOICE, path="x.pdf", received_on=date(2026, 9, 1)),
        ])
    insert(g_conn, [
        Bill(
            business_id="b1", bill_id="bill_1", vendor_id="v1", doc_id="inv_1",
            invoice_number="INV-1", printed_vendor_name="Acme Co", issue_date=date(2026, 9, 1),
            stated_due_date=date(2026, 9, 15), due_date_derived=date(2026, 9, 15),
            payment_terms_raw="Net 15", currency="USD",
            subtotal=Decimal("10.00"), tax=Decimal("1.00"), total=Decimal("11.00"),
            remit_account_last4="1234",
        ),
        *[
            BillLine(business_id="b1", bill_id="bill_1", line_no=idx, description=ln[0], quantity=ln[1], unit_price=ln[2], line_total=ln[3], evidence_id=f"span_inv_1_line{idx}")
            for idx, ln in enumerate(g_lines, start=1)
        ],
    ])
    insert(e_conn, [
        Bill(
            business_id="b1", bill_id="bill_1", vendor_id="v1", doc_id="inv_1",
            invoice_number="INV-1", printed_vendor_name="Acme Co", issue_date=date(2026, 9, 1),
            stated_due_date=date(2026, 9, 15), due_date_derived=date(2026, 9, 15),
            payment_terms_raw="Net 15", currency="USD",
            subtotal=None, tax=None, total=Decimal("12.00"),  # subtotal/tax missed (2 FN), total wrong (1 FP + 1 FN)
            remit_account_last4="1234",
        ),
        *[
            BillLine(business_id="b1", bill_id="bill_1", line_no=idx, description=ln[0], quantity=ln[1], unit_price=ln[2], line_total=ln[3], evidence_id=f"span_inv_1_line{idx}")
            for idx, ln in enumerate(p_lines, start=1)
        ],
    ])

    res = em.evaluate_bundle_stores(Store(g_conn, "b1"), Store(e_conn, "b1"))
    assert res["fields"]["vendor"] == {"tp": 1, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert res["fields"]["subtotal"] == {"tp": 0, "fp": 0, "fn": 1, "precision": None, "recall": 0.0, "f1": None}
    assert res["fields"]["total"] == {"tp": 0, "fp": 1, "fn": 1, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    assert res["fields"]["line_items"] == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5, "f1": 0.5}

    # Tiny SROIE jsonl test
    sroie_p = tmp_path / "sroie.jsonl"
    sroie_p.write_text(
        "\n".join([
            json.dumps({"id": "1", "pred": {"vendor": "ACME BND", "date": "25/12/2018", "total": "9.00"}, "gold": {"company": "ACME BHD", "date": "25/12/2018", "total": "9.00"}}),
            json.dumps({"id": "2", "pred": {"vendor": "BETA SHOP", "date": "01/02/2019", "total": "10.00"}, "gold": {"company": "BETA SHOP", "date": "01/02/2019", "total": "10.00"}}),
        ])
        + "\n",
        encoding="utf-8",
    )
    sr = em.evaluate_sroie_jsonl(sroie_p)
    assert sr["fields"]["company"] == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5, "f1": 0.5}
    assert sr["fields"]["date"]["f1"] == 1.0
    assert sr["fields"]["total"]["f1"] == 1.0


def test_item4_citation_mean_f1_and_micro_f1():
    lm = _load_mod("lecture_metrics", PROJECT / "evaluation" / "lecture_metrics.py")

    # Turn 0: gold=1, pred=1, tp=1 -> P=1.0, R=1.0, F1=1.0
    # Turn 1: gold=3, pred=2, tp=1 -> P=0.5, R=1/3, F1=0.4
    # Turn 2: gold=0 (None P/R, skipped)
    # Mean F1 = (1.0 + 0.4) / 2 = 0.7
    # Micro P = 2/3, Micro R = 2/4 = 0.5 -> Micro F1 = 2*(2/3)*0.5 / (2/3 + 0.5) = 4/7
    rows = [
        _mk_row("C3", "Q01", 0, Answerability.ANSWER, "ANSWER", er=1.0, ep=1.0),
        _mk_row("C3", "Q02", 0, Answerability.ANSWER, "ANSWER", er=1 / 3, ep=0.5),
        _mk_row("C3", "Q03", 0, Answerability.CLARIFY, "CLARIFY", er=None, ep=None),
    ]
    gold_counts = {("mini", "Q01", 0): 1, ("mini", "Q02", 0): 3}
    cf1 = lm.compute_citation_f1(rows, gold_counts)["C3"]
    assert cf1["turns_with_gold_cites"] == 2
    assert cf1["mean_f1"] == pytest.approx(0.7)
    assert cf1["micro_precision"] == pytest.approx(2 / 3)
    assert cf1["micro_recall"] == pytest.approx(0.5)
    assert cf1["micro_f1"] == pytest.approx(4 / 7)
