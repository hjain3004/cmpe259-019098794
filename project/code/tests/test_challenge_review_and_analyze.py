"""Tests for evaluation/challenge/review_sheet.py and evaluation/challenge/analyze.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[2]
VENV_PYTHON = Path(sys.executable)


def _load(name: str, rel_path: str):
    path = PROJECT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_tiny_run(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal self-contained challenge run folder exercising every attribution cause."""
    run_dir = tmp_path / "challenge_run"
    run_dir.mkdir(parents=True)

    ledger = {
        "business": {"business_id": "tiny_01", "name": "Tiny Cafe", "evaluation_clock": "2026-09-24"},
        "vendors": [
            {
                "vendor_id": "v_north",
                "canonical_name": "Northside",
                "verified_payment": {
                    "bank_name": "Bay Bank",
                    "account_number": "004417829931",
                    "routing_number": "121000358",
                },
            }
        ],
        "invoices": [
            {
                "invoice_number": "NS-1048",
                "vendor_id": "v_north",
                "issue_date": "2026-08-20",
                "stated_due_date": "2026-09-19",
                "currency": "USD",
                "subtotal": "777.85",
                "tax": "64.15",
                "total": "842.00",
                "remit": {"bank_name": "Bay Bank", "account_number": "008812345507"},
            },
            {
                "invoice_number": "NS-1050",
                "vendor_id": "v_north",
                "issue_date": "2026-09-01",
                "stated_due_date": "2026-10-01",
                "currency": "USD",
                "subtotal": "200.00",
                "tax": "0.00",
                "total": "200.00",
                "remit": {"bank_name": "Bay Bank", "account_number": "004417829931"},
            },
        ],
    }
    (run_dir / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    gold = {
        "CH01_pass": {
            "turns": [
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"total": "842.00 USD"},
                    "rubric": "Must state the exact invoice total clearly.",
                }
            ]
        },
        "CH02_test_design": {
            "turns": [
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"total": "200.00 USD"},
                    "rubric": "Explain due date clearly.",
                }
            ]
        },
        "CH03_extraction": {
            "turns": [
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"total": "842.00 USD"},
                }
            ]
        },
        "CH04_dialogue": {
            "turns": [
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"invoice": "NS-1048"},
                },
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"total": "842.00 USD"},
                },
            ]
        },
        "CH05_budget": {
            "turns": [
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"total": "200.00 USD"},
                }
            ]
        },
        "CH06_orchestration": {
            "turns": [
                {
                    "allowed": ["WARN", "ANSWER"],
                    "required_values": {"verified_last4": "9931"},
                }
            ]
        },
        "CH07_tool_coverage": {
            "turns": [
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"carrier_tracking": "1Z999AA101"},
                }
            ]
        },
        "CH08_generation": {
            "turns": [
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"total": "842.00 USD"},
                }
            ]
        },
        "CH09_needs_human": {
            "turns": [
                {
                    "allowed": ["ANSWER"],
                    "required_values": {"total": "200.00 USD"},
                    "rubric": "Provide a clear breakdown.",
                }
            ]
        },
    }
    (run_dir / "gold.yaml").write_text(yaml.safe_dump(gold, sort_keys=False), encoding="utf-8")

    def _row(
        qid: str,
        ti: int,
        text: str,
        raw: str,
        success: bool,
        scores: dict,
        tools: list[dict],
    ) -> dict:
        return {
            "query_id": qid,
            "turn_index": ti,
            "turn_text": text,
            "configuration": "C3",
            "raw_response": raw,
            "parsed_ok": scores.get("parsed", True),
            "expected": "ANSWER",
            "success": success,
            "scores": scores,
            "notes": "",
            "context": tools,
        }

    inv_ok_tool = {
        "tool": "get_bill_status",
        "args": {"invoice_number": "NS-1048", "account_hint": "008812345507"},
        "result": json.dumps({"bill": {"invoice_number": "NS-1048", "total": {"amount": "842.00", "currency": "USD"}}}),
    }
    inv_bad_tool = {
        "tool": "get_bill_status",
        "args": {"invoice_number": "NS-1048"},
        "result": json.dumps({"bill": {"invoice_number": "NS-1048", "total": {"amount": "999.00", "currency": "USD"}}}),
    }
    inv_200_tool = {
        "tool": "get_bill_status",
        "args": {"invoice_number": "NS-1050"},
        "result": json.dumps({"bill": {"invoice_number": "NS-1050", "total": {"amount": "200.00", "currency": "USD"}}}),
    }

    rows = [
        _row(
            "CH01_pass",
            0,
            "What is the total of NS-1048?",
            json.dumps({"answerability": "ANSWER", "answer": "NS-1048 totals $842.00 USD (acct 008812345507)."}),
            True,
            {"parsed": True, "answerability_ok": True, "values": {"total": True}},
            [inv_ok_tool],
        ),
        _row(
            "CH02_test_design",
            0,
            "What is due on NS-1050?",
            json.dumps({"answerability": "ANSWER", "answer": "NS-1050 totals $200.00 USD."}),
            True,
            {"parsed": True, "answerability_ok": True, "values": {"total": True}},
            [inv_200_tool],
        ),
        _row(
            "CH03_extraction",
            0,
            "What is the total of NS-1048?",
            json.dumps({"answerability": "ANSWER", "answer": "NS-1048 totals $999.00 USD."}),
            False,
            {"parsed": True, "answerability_ok": True, "values": {"total": False}},
            [inv_bad_tool],
        ),
        _row(
            "CH04_dialogue",
            0,
            "Look up NS-1048.",
            json.dumps({"answerability": "ANSWER", "answer": "Found NS-1048."}),
            True,
            {"parsed": True, "answerability_ok": True, "values": {"invoice": True}},
            [inv_ok_tool],
        ),
        _row(
            "CH04_dialogue",
            1,
            "What is its total?",
            json.dumps({"answerability": "ANSWER", "answer": "NS-1050 is $200.00 USD."}),
            False,
            {"parsed": True, "answerability_ok": True, "values": {"total": False}},
            [inv_200_tool],
        ),
        _row(
            "CH05_budget",
            0,
            "Find the invoice totaling 200.00.",
            json.dumps({"answerability": "ABSTAIN", "answer": "Stopped after multiple searches."}),
            False,
            {"parsed": True, "answerability_ok": False, "values": {"total": False}},
            [{"tool": "list_open_bills", "args": {"page": i}, "result": "{}"} for i in range(6)],
        ),
        _row(
            "CH06_orchestration",
            0,
            "Did the bank account on NS-1048 change from our verified record?",
            json.dumps({"answerability": "ANSWER", "answer": "NS-1048 is $842.00 USD."}),
            False,
            {"parsed": True, "answerability_ok": True, "values": {"verified_last4": False}},
            [inv_ok_tool],
        ),
        _row(
            "CH07_tool_coverage",
            0,
            "What is the carrier tracking number on NS-1048?",
            json.dumps({"answerability": "ABSTAIN", "answer": "No tracking number appears in the tool outputs."}),
            False,
            {"parsed": True, "answerability_ok": False, "values": {"carrier_tracking": False}},
            [inv_ok_tool],
        ),
        _row(
            "CH08_generation",
            0,
            "What is the total of NS-1048?",
            json.dumps({"answerability": "ANSWER", "answer": "NS-1048 is a Northside bill."}),
            False,
            {"parsed": True, "answerability_ok": True, "values": {"total": False}},
            [inv_ok_tool],
        ),
        _row(
            "CH09_needs_human",
            0,
            "Break down NS-1050.",
            json.dumps({"answerability": "ANSWER", "answer": "NS-1050 is $200.00 USD."}),
            True,
            {"parsed": True, "answerability_ok": True, "values": {"total": True}},
            [inv_200_tool],
        ),
    ]
    (run_dir / "log.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    human_csv = run_dir / "human_scores.csv"
    with open(human_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["query_id", "turn_index", "configuration", "rubric_score", "notes"])
        w.writerow(["CH01_pass", 0, "C3", "2", "Accurate and complete"])
        w.writerow(["CH02_test_design", 0, "C3", "0", "TEST: prompt asks wrong question"])
        w.writerow(["CH09_needs_human", 0, "C3", "0", "Explanation too brief"])

    return run_dir, human_csv


def test_review_sheet_html_structure_masking_and_controls(tmp_path: Path):
    run_dir, _ = _build_tiny_run(tmp_path)
    review_mod = _load("challenge_review_sheet", "evaluation/challenge/review_sheet.py")
    out_html = review_mod.generate_review_sheet(run_dir)
    assert out_html == run_dir / "review.html"
    content = out_html.read_text(encoding="utf-8")

    # Self-contained: no external scripts or stylesheets
    assert "http://" not in content and "https://" not in content
    assert "<button type=\"button\" id=\"export-csv-btn\">Export CSV</button>" in content
    assert "query_id,turn_index,configuration,rubric_score,notes" in content
    assert "human_scores.csv" in content

    # Account numbers masked to last 4 digits in both reply text and tool args
    assert "008812345507" not in content
    assert "****5507" in content

    # Required sections rendered
    assert "CH01_pass" in content
    assert "Allowed types:" in content
    assert "Required values:" in content
    assert "Deterministic checks:" in content
    assert "get_bill_status(" in content

    # Exactly the 3 rubric turns get 0/1/2 controls (CH01_pass, CH02_test_design, CH09_needs_human)
    assert content.count('class="rubric-score"') == 3
    assert content.count('class="rubric-notes"') == 3


def test_analyze_failure_causes_and_combined_table(tmp_path: Path):
    run_dir, human_csv = _build_tiny_run(tmp_path)
    analyze_mod = _load("challenge_analyze", "evaluation/challenge/analyze.py")
    out_md = analyze_mod.analyze_run(run_dir, human_csv=human_csv)
    assert out_md == run_dir / "analysis.md"
    md = out_md.read_text(encoding="utf-8")

    # Summary checks: 10 turns total, 8 failing/0-rubric analyzed (CH01_pass and CH04 t0 pass)
    assert "- Scored turns: 10" in md
    assert "- Failing or 0-rubric turns analyzed: 8" in md

    # Combined pass table:
    # Det pass = 4 (CH01_pass, CH02_test_design, CH04 t0, CH09_needs_human)
    # Rubric scored = 3 (CH01=2, CH02=0, CH09=0) -> Rubric >= 1 = 1/3
    # Combined pass (Det AND Rubric >= 1, with non-rubric needing Det pass) = 2/10 (20%)
    assert "| C3 | 10 | 4/10 | 3 | 1/3 | 2/10 (20%) |" in md

    # Every cause counted accurately (1 each)
    for cause in (
        "test_design",
        "extraction",
        "dialogue_state",
        "tool_budget",
        "orchestration",
        "tool_coverage",
        "generation",
        "needs human tagging",
    ):
        assert f"| {cause} | 1 |" in md

    # Spot-check per-turn attribution rows
    assert "| CH02_test_design | 0 | C3 | PASS | 0 | `test_design` |" in md
    assert "| CH03_extraction | 0 | C3 | FAIL | — | `extraction` |" in md
    assert "| CH04_dialogue | 1 | C3 | FAIL | — | `dialogue_state` |" in md
    assert "| CH05_budget | 0 | C3 | FAIL | — | `tool_budget` |" in md
    assert "| CH06_orchestration | 0 | C3 | FAIL | — | `orchestration` |" in md
    assert "| CH07_tool_coverage | 0 | C3 | FAIL | — | `tool_coverage` |" in md
    assert "| CH08_generation | 0 | C3 | FAIL | — | `generation` |" in md
    assert "| CH09_needs_human | 0 | C3 | PASS | 0 | `needs human tagging` |" in md


def test_challenge_scripts_cli_smoke(tmp_path: Path):
    run_dir, human_csv = _build_tiny_run(tmp_path)
    r1 = subprocess.run(
        [str(VENV_PYTHON), str(PROJECT / "evaluation" / "challenge" / "review_sheet.py"), str(run_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "review.html" in r1.stdout
    assert (run_dir / "review.html").exists()

    r2 = subprocess.run(
        [
            str(VENV_PYTHON),
            str(PROJECT / "evaluation" / "challenge" / "analyze.py"),
            str(run_dir),
            "--human",
            str(human_csv),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "analysis.md" in r2.stdout
    assert (run_dir / "analysis.md").exists()
