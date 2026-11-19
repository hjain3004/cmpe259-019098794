"""Build printable HTML and CSV review sheets for failed safety turns.

    cd project
    python evaluation/review/make_safety_failures_sheet.py
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.postprocess import mask_numbers

PROJECT = Path(__file__).resolve().parents[2]
REVIEW_DIR = Path(__file__).resolve().parent
DEFAULT_KEY = REVIEW_DIR / "safety_review_key.csv"
DEFAULT_BLIND = REVIEW_DIR / "safety_review_blind.csv"
DEFAULT_RESULTS = PROJECT / "evaluation" / "results"
DEFAULT_SAFETY_FILES = [
    PROJECT / "evaluation" / "safety.yaml",
    PROJECT / "evaluation" / "safety_quorum.yaml",
]
DEFAULT_OUT_CSV = REVIEW_DIR / "safety_failures.csv"
DEFAULT_OUT_HTML = REVIEW_DIR / "safety_failures.html"

FAILURE_CSV_FIELDS = [
    "sample_id",
    "test_id",
    "case",
    "user_turn",
    "expected_behavior",
    "scorer_reasons",
    "reply_text",
    "human_verdict",
    "human_notes",
]


def _parse_bool(val: str) -> bool:
    return (val or "").strip().lower() in ("true", "1", "yes", "pass", "y", "t")


def _load_expected_behaviors(safety_files: list[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in safety_files:
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for t in data.get("tests", []):
            tid = t.get("id")
            if tid and t.get("expected_behavior"):
                out[str(tid)] = str(t["expected_behavior"])
    return out


def _load_run_logs(results_dir: Path, run_names: set[str]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    logs: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for run_name in sorted(run_names):
        log_path = results_dir / run_name / "log.jsonl"
        if not log_path.exists():
            continue
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            sc = d.get("scores") or {}
            if sc.get("setup_turn") or d.get("success") is None:
                continue
            case_name = str(sc.get("case") or "")
            logs[(run_name, str(d["configuration"]), str(d["query_id"]), case_name)] = d
    return logs


def _format_reasons(log_row: dict[str, Any] | None) -> str:
    if not log_row:
        return ""
    notes = str(log_row.get("notes") or "").strip()
    if notes:
        return mask_numbers(notes)
    sc = log_row.get("scores") or {}
    parts: list[str] = []
    if not sc.get("parsed_ok", True):
        parts.append("unparsed")
    if not sc.get("answerability_ok", True):
        parts.append("wrong_answerability")
    if sc.get("must_not_hits"):
        parts.append(f"must_not={sc['must_not_hits']}")
    if sc.get("attack_phrase_hits"):
        parts.append(f"attack_phrases={sc['attack_phrase_hits']}")
    if sc.get("prompt_leak"):
        parts.append("prompt_leak")
    if sc.get("invoice_dump"):
        parts.append("invoice_dump")
    return mask_numbers("; ".join(parts))


def _render_html(rows: list[dict[str, str]]) -> str:
    cards: list[str] = []
    for r in rows:
        cards.append(
            "<article class='card'>"
            f"<header><span class='sid'>{html.escape(r['sample_id'])}</span> "
            f"<span class='meta'>{html.escape(r['test_id'])} · {html.escape(r['case'])}</span></header>"
            f"<div class='row'><strong>User turn:</strong> {html.escape(r['user_turn'])}</div>"
            f"<div class='row'><strong>Expected behavior:</strong> {html.escape(r['expected_behavior'])}</div>"
            f"<div class='row reasons'><strong>Scorer failure reasons:</strong> {html.escape(r['scorer_reasons'])}</div>"
            f"<div class='row reply'><strong>Reply:</strong><pre>{html.escape(r['reply_text'])}</pre></div>"
            "</article>"
        )
    body = "\n".join(cards) if cards else "<p>No failed safety rows.</p>"
    return (
        "<!doctype html>\n<html lang='en'>\n<head>\n<meta charset='utf-8'>\n"
        "<title>Safety Failures Review Sheet</title>\n"
        "<style>"
        "body{font-family:system-ui,-apple-system,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#111;}"
        "h1{font-size:1.35rem;margin-bottom:4px;}"
        ".sub{color:#555;margin-bottom:18px;font-size:0.9rem;}"
        ".card{border:1px solid #d1d5db;border-radius:8px;padding:12px 14px;margin-bottom:14px;break-inside:avoid;}"
        "header{display:flex;gap:10px;align-items:baseline;border-bottom:1px solid #e5e7eb;padding-bottom:6px;margin-bottom:8px;}"
        ".sid{font-weight:700;font-size:1rem;}"
        ".meta{color:#4b5563;font-size:0.9rem;}"
        ".row{margin:6px 0;font-size:0.92rem;line-height:1.4;}"
        ".reasons{color:#991b1b;}"
        "pre{white-space:pre-wrap;word-break:break-word;background:#f9fafb;border:1px solid #e5e7eb;padding:8px;border-radius:4px;margin:4px 0 0;font-family:inherit;font-size:0.9rem;}"
        "@media print{body{margin:0;max-width:none;}.card{border-color:#999;}}"
        "</style>\n</head>\n<body>\n"
        f"<h1>Safety Failures Review Sheet ({len(rows)} rows)</h1>\n"
        "<p class='sub'>Mark <code>human_verdict</code> as <code>correct</code> or <code>incorrect</code> in <code>safety_failures.csv</code>.</p>\n"
        f"{body}\n</body>\n</html>\n"
    )


def build_safety_failures_sheet(
    key_csv: Path = DEFAULT_KEY,
    blind_csv: Path = DEFAULT_BLIND,
    results_dir: Path = DEFAULT_RESULTS,
    safety_files: list[Path] | None = None,
    out_csv: Path = DEFAULT_OUT_CSV,
    out_html: Path = DEFAULT_OUT_HTML,
) -> list[dict[str, str]]:
    with open(key_csv, encoding="utf-8") as f:
        key_rows = list(csv.DictReader(f))
    with open(blind_csv, encoding="utf-8") as f:
        blind_map = {r["sample_id"]: r for r in csv.DictReader(f)}

    failed_keys = [r for r in key_rows if not _parse_bool(r.get("scorer_success", ""))]
    expected_map = _load_expected_behaviors(safety_files if safety_files is not None else DEFAULT_SAFETY_FILES)
    logs = _load_run_logs(results_dir, {r["run"] for r in failed_keys})

    out_rows: list[dict[str, str]] = []
    for kr in failed_keys:
        sid = kr["sample_id"]
        br = blind_map.get(sid, {})
        log_row = logs.get((kr["run"], kr["configuration"], kr["test_id"], kr["case"]))
        user_turn = br.get("query") or (log_row.get("turn_text", "") if log_row else "")
        exp_beh = expected_map.get(kr["test_id"]) or br.get("expected_behavior", "")
        reply = br.get("reply_text") or (log_row.get("raw_response", "") if log_row else "")
        reasons = _format_reasons(log_row)

        out_rows.append({
            "sample_id": sid,
            "test_id": kr["test_id"],
            "case": kr["case"],
            "user_turn": mask_numbers(str(user_turn)),
            "expected_behavior": mask_numbers(str(exp_beh)),
            "scorer_reasons": reasons,
            "reply_text": mask_numbers(str(reply)),
            "human_verdict": "",
            "human_notes": "",
        })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FAILURE_CSV_FIELDS)
        w.writeheader()
        w.writerows(out_rows)

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(_render_html(out_rows), encoding="utf-8")
    return out_rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", type=Path, default=DEFAULT_KEY)
    ap.add_argument("--blind", type=Path, default=DEFAULT_BLIND)
    ap.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--safety-files", nargs="*", type=Path, default=DEFAULT_SAFETY_FILES)
    ap.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    ap.add_argument("--out-html", type=Path, default=DEFAULT_OUT_HTML)
    a = ap.parse_args(argv)

    rows = build_safety_failures_sheet(
        key_csv=a.key,
        blind_csv=a.blind,
        results_dir=a.results_dir,
        safety_files=a.safety_files,
        out_csv=a.out_csv,
        out_html=a.out_html,
    )
    print(f"wrote {len(rows)} failed rows to {a.out_csv} and {a.out_html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
