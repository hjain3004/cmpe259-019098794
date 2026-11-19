"""Summarize classmate demo session logs and export peer questions in queries.yaml format.

    cd project
    ../.venv/bin/python evaluation/peer_summary.py
    ../.venv/bin/python evaluation/peer_summary.py --sessions demo/sessions \
        --summary-out evaluation/results/peer_testing/summary.md \
        --yaml-out evaluation/results/peer_testing/peer_queries.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import ConversationSpec, QuerySuite, TurnSpec
from cashbooks.contracts.postprocess import mask_numbers

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS = PROJECT / "demo" / "sessions"
DEFAULT_OUT_DIR = PROJECT / "evaluation" / "results" / "peer_testing"
DEFAULT_SUMMARY = DEFAULT_OUT_DIR / "summary.md"
DEFAULT_YAML = DEFAULT_OUT_DIR / "peer_queries.yaml"

_VALID_ANS = {a.value for a in Answerability}


def _escape_md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def load_session_records(sessions_dir: Path = DEFAULT_SESSIONS) -> list[dict[str, Any]]:
    """Load and normalize all turn records from sessions_dir/*.jsonl."""
    records: list[dict[str, Any]] = []
    if not sessions_dir.exists():
        return records

    for path in sorted(sessions_dir.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                raw = json.loads(line)
                q = mask_numbers(str(raw.get("question") or "").strip())
                if not q:
                    continue
                reply = mask_numbers(str(raw.get("reply") or raw.get("masked_answer") or "").strip())
                cfg = str(raw.get("configuration") or raw.get("config") or "C3").strip() or "C3"
                thumbs = raw.get("thumbs")
                if thumbs not in ("up", "down"):
                    thumbs = None
                records.append({
                    "tester": str(raw.get("tester") or "anonymous").strip() or "anonymous",
                    "timestamp": str(raw.get("timestamp") or "").strip(),
                    "bundle": str(raw.get("bundle") or "cafe_01").strip() or "cafe_01",
                    "configuration": cfg,
                    "question": q,
                    "reply": reply,
                    "answerability": raw.get("answerability"),
                    "cited_ids": list(raw.get("cited_ids") or []),
                    "latency_ms": int(raw.get("latency_ms") or 0),
                    "thumbs": thumbs,
                    "comment": mask_numbers(str(raw.get("comment") or "").strip()),
                    "source_file": path.name,
                })
    return records


def summarize_by_tester(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate question counts, thumbs up/down counts, and comments per tester."""
    by_tester: dict[str, dict[str, Any]] = {}
    for rec in records:
        tester = rec["tester"]
        entry = by_tester.setdefault(
            tester,
            {
                "tester": tester,
                "bundles": [],
                "configs": [],
                "questions": 0,
                "thumbs_up": 0,
                "thumbs_down": 0,
                "unrated": 0,
                "comments": [],
            },
        )
        if rec["bundle"] not in entry["bundles"]:
            entry["bundles"].append(rec["bundle"])
        if rec["configuration"] not in entry["configs"]:
            entry["configs"].append(rec["configuration"])
        entry["questions"] += 1
        if rec["thumbs"] == "up":
            entry["thumbs_up"] += 1
        elif rec["thumbs"] == "down":
            entry["thumbs_down"] += 1
        else:
            entry["unrated"] += 1
        if rec["comment"]:
            entry["comments"].append(rec["comment"])
    return list(by_tester.values())


def build_peer_query_suite(
    records: list[dict[str, Any]],
    evaluation_clock: date = date(2026, 9, 24),
) -> dict[str, Any]:
    """Build a queries.yaml-compatible payload (validated against QuerySuite when non-empty)."""
    conversations: list[dict[str, Any]] = []
    for idx, rec in enumerate(records[:99], start=1):
        qid = f"Q{idx:02d}"
        ans_raw = str(rec.get("answerability") or "ANSWER").upper()
        expected = ans_raw if ans_raw in _VALID_ANS else "ANSWER"
        note_parts = [
            f"tester={rec['tester']}",
            f"bundle={rec['bundle']}",
            f"config={rec['configuration']}",
        ]
        if rec["thumbs"]:
            note_parts.append(f"thumbs={rec['thumbs']}")
        if rec["comment"]:
            note_parts.append(f"comment={rec['comment']}")

        conv_dict: dict[str, Any] = {
            "id": qid,
            "category": "common",
            "scenario": f"peer session question from {rec['tester']} on {rec['bundle']} ({rec['configuration']})",
            "labels": ["lookup"],
            "turns": [
                {
                    "text": rec["question"],
                    "scored": True,
                    "expected": expected,
                    "expected_behavior": (
                        f"Answer peer question from {rec['bundle']} records with supporting citations."
                    ),
                }
            ],
            "notes": "; ".join(note_parts),
        }
        ConversationSpec.model_validate(conv_dict)
        conversations.append(conv_dict)

    payload: dict[str, Any] = {
        "version": "0.1",
        "evaluation_clock": evaluation_clock,
        "status": "draft",
        "conversations": conversations,
    }
    if conversations:
        QuerySuite.model_validate(payload)
    return payload


def render_summary_markdown(records: list[dict[str, Any]], tester_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Peer Testing Summary",
        "",
        f"Total logged questions: **{len(records)}** across **{len(tester_rows)}** tester(s).",
        "",
        "## Per-Tester Summary",
        "",
        "| Tester | Bundle(s) | Config(s) | Questions | Thumbs up | Thumbs down | Comments |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not tester_rows:
        lines.append("| *(no sessions logged yet)* | — | — | 0 | 0 | 0 | — |")
    else:
        for row in tester_rows:
            comments_str = "; ".join(_escape_md(c) for c in row["comments"]) if row["comments"] else "—"
            bundles_str = ", ".join(row["bundles"])
            configs_str = ", ".join(row["configs"])
            lines.append(
                f"| {_escape_md(row['tester'])} | {_escape_md(bundles_str)} | {_escape_md(configs_str)} "
                f"| {row['questions']} | {row['thumbs_up']} | {row['thumbs_down']} | {comments_str} |"
            )

    if records:
        lines.extend([
            "",
            "## Logged Questions & Replies",
            "",
            "| # | Tester | Bundle | Config | Question | Reply | Thumbs | Comment |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for i, rec in enumerate(records, start=1):
            thumbs_str = rec["thumbs"] or "—"
            comment_str = _escape_md(rec["comment"]) if rec["comment"] else "—"
            lines.append(
                f"| {i} | {_escape_md(rec['tester'])} | {_escape_md(rec['bundle'])} | {_escape_md(rec['configuration'])} "
                f"| {_escape_md(rec['question'])} | {_escape_md(rec['reply'])} | {thumbs_str} | {comment_str} |"
            )

    lines.append("")
    return "\n".join(lines)


def write_peer_summary(
    sessions_dir: Path = DEFAULT_SESSIONS,
    summary_out: Path = DEFAULT_SUMMARY,
    yaml_out: Path = DEFAULT_YAML,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read all session logs, write summary.md and peer_queries.yaml, and return (tester_rows, suite_dict)."""
    records = load_session_records(sessions_dir)
    tester_rows = summarize_by_tester(records)
    suite_payload = build_peer_query_suite(records)

    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(render_summary_markdown(records, tester_rows), encoding="utf-8")

    yaml_out.parent.mkdir(parents=True, exist_ok=True)
    yaml_out.write_text(yaml.safe_dump(suite_payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    return tester_rows, suite_payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize peer testing session logs and export peer queries YAML.")
    ap.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS)
    ap.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    ap.add_argument("--yaml-out", type=Path, default=DEFAULT_YAML)
    a = ap.parse_args(argv)

    tester_rows, suite_payload = write_peer_summary(a.sessions, a.summary_out, a.yaml_out)
    n_questions = len(suite_payload["conversations"])
    print(f"summarized {n_questions} question(s) from {len(tester_rows)} tester(s) -> {a.summary_out} and {a.yaml_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
