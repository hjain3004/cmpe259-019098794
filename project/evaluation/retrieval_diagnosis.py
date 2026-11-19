"""Diagnose C1 and C2 retrieval recall@k and failure modes from saved run logs.

    cd project
    python evaluation/retrieval_diagnosis.py evaluation/results/<run_id> [...]

Writes retrieval.md into each run folder (reading rescored/log.jsonl if present).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.evaluation import LogRow, QuerySuite
from cashbooks.scoring import doc_level, read_log

PROJECT = Path(__file__).resolve().parents[1]
LABELS = ["lookup", "aggregation", "temporal", "linking", "comparison", "dialogue", "abstention"]


def doc_type(doc_id: str) -> str:
    if doc_id.startswith("inv_"):
        return "invoice"
    if doc_id.startswith("txn_"):
        return "bank row"
    if doc_id.startswith("msg_"):
        return "message"
    if doc_id.startswith("vh_"):
        return "vendor record"
    if doc_id.startswith("cn_"):
        return "credit note"
    return "other"


def _resolve_log_and_bundle(run_dir: Path) -> tuple[Path, Path]:
    rescored = run_dir / "rescored"
    src_dir = rescored if (rescored / "log.jsonl").exists() else run_dir
    log_path = src_dir / "log.jsonl"

    bundle: Path | None = None
    for cand in (src_dir / "summary.json", run_dir / "summary.json"):
        if cand.exists():
            meta = json.loads(cand.read_text(encoding="utf-8"))
            if meta.get("bundle"):
                b = Path(meta["bundle"])
                bundle = b if b.is_absolute() else (PROJECT / b)
                break
    if bundle is None:
        rows = read_log(log_path)
        scen = rows[0].scenario if rows else "cafe_01"
        bundle = PROJECT / "data" / "dev" / scen
    return log_path, bundle


def classify_failure(row: LogRow, gold_evidence: list[str], missed_docs: list[str]) -> str:
    """Classify a failed C1/C2 turn into (a)-(d)."""
    if not gold_evidence:
        return "other"
    if missed_docs:
        return "retrieval miss"
    if not row.parsed_ok or (row.scores.get("must_not_hits") or []):
        return "other"
    if not row.scores.get("answerability_ok", False):
        return "evidence retrieved, wrong reply type"
    vals = row.scores.get("values") or {}
    if vals and not all(vals.values()):
        return "evidence retrieved, wrong value"
    return "other"


def analyze_run(
    run_dir: Path,
    queries_path: Path = PROJECT / "evaluation" / "queries.yaml",
    bundle_override: Path | None = None,
) -> dict[str, Any]:
    log_path, bundle = _resolve_log_and_bundle(run_dir)
    if bundle_override is not None:
        bundle = bundle_override
    suite = QuerySuite.model_validate(yaml.safe_load(queries_path.read_text(encoding="utf-8")))
    specs = {c.id: c for c in suite.conversations}
    gold = yaml.safe_load((bundle / "gold.yaml").read_text(encoding="utf-8"))

    rows = [
        r for r in read_log(log_path)
        if r.configuration in ("C1", "C2") and not r.scores.get("setup_turn") and r.success is not None
    ]

    turn_records: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []

    for r in rows:
        spec = specs.get(r.query_id)
        gold_ev: list[str] = []
        labels: list[str] = []
        if spec is not None:
            labels = list(spec.labels)
            gi = sum(1 for t in spec.turns[: r.turn_index] if t.scored)
            g_entry = gold.get(r.query_id, [])
            g_list = g_entry["turns"] if isinstance(g_entry, dict) else g_entry
            if gi < len(g_list):
                gold_ev = list(g_list[gi].get("evidence") or [])

        retrieved_chunks = [c.get("chunk_id", "") for c in (r.context or []) if isinstance(c, dict)]
        k = len(retrieved_chunks)
        retrieved_docs = {doc_level(cid) for cid in retrieved_chunks if cid}
        missed_docs = [g for g in gold_ev if g not in retrieved_docs]
        recall = (len(gold_ev) - len(missed_docs)) / len(gold_ev) if gold_ev else None

        fail_cat = None if r.success else classify_failure(r, gold_ev, missed_docs)
        rec = {
            "configuration": r.configuration,
            "query_id": r.query_id,
            "turn_index": r.turn_index,
            "turn_text": r.turn_text,
            "labels": labels,
            "k": k,
            "gold_evidence": gold_ev,
            "missed_docs": missed_docs,
            "recall_at_k": recall,
            "success": bool(r.success),
            "failure_category": fail_cat,
        }
        turn_records.append(rec)
        if fail_cat == "retrieval miss":
            for mdoc in missed_docs:
                misses.append({
                    "configuration": r.configuration,
                    "query_id": r.query_id,
                    "turn_index": r.turn_index,
                    "doc_id": mdoc,
                    "doc_type": doc_type(mdoc),
                    "turn_text": r.turn_text,
                })

    return {
        "run_name": run_dir.name,
        "source": str(log_path.relative_to(run_dir)) if log_path.is_relative_to(run_dir) else str(log_path),
        "turns": turn_records,
        "misses": misses,
    }


def format_retrieval_md(analysis: dict[str, Any]) -> str:
    turns = analysis["turns"]
    misses = analysis["misses"]
    configs = sorted({t["configuration"] for t in turns})

    lines = [
        f"# Retrieval Diagnosis ({analysis['run_name']})",
        "",
        f"Source: `{analysis['source']}`.",
        "",
        "## Overall mean recall@k and failure breakdown",
        "",
        "| Config | Scored turns | Mean recall@k | Retrieval miss | Wrong reply type | Wrong value | Other |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    cats = [
        "retrieval miss",
        "evidence retrieved, wrong reply type",
        "evidence retrieved, wrong value",
        "other",
    ]
    for cfg in configs:
        ct = [t for t in turns if t["configuration"] == cfg]
        recs = [t["recall_at_k"] for t in ct if t["recall_at_k"] is not None]
        mean_r = f"{sum(recs) / len(recs):.3f}" if recs else "n/a"
        counts = [sum(1 for t in ct if t["failure_category"] == c) for c in cats]
        lines.append(f"| {cfg} | {len(ct)} | {mean_r} | " + " | ".join(str(x) for x in counts) + " |")

    lines += [
        "",
        "## Mean recall@k by question-type label",
        "",
        "| Label | " + " | ".join(configs) + " |",
        "| --- |" + " --- |" * len(configs),
    ]
    for lbl in LABELS:
        cells = []
        for cfg in configs:
            recs = [
                t["recall_at_k"]
                for t in turns
                if t["configuration"] == cfg and lbl in t["labels"] and t["recall_at_k"] is not None
            ]
            cells.append(f"{sum(recs) / len(recs):.3f} (n={len(recs)})" if recs else "n/a")
        lines.append(f"| {lbl} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Retrieval misses by document type",
        "",
        "| Config | Document type | Misses |",
        "| --- | --- | --- |",
    ]
    for cfg in configs:
        by_dt: dict[str, int] = defaultdict(int)
        for m in misses:
            if m["configuration"] == cfg:
                by_dt[m["doc_type"]] += 1
        for dt, cnt in sorted(by_dt.items()):
            lines.append(f"| {cfg} | {dt} | {cnt} |")

    lines += [
        "",
        "## Retrieval miss details",
        "",
        "| Config | Query | Turn | Missed doc | Doc type | Turn text |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for m in misses:
        txt = m["turn_text"].replace("|", "\\|")
        lines.append(
            f"| {m['configuration']} | {m['query_id']} | {m['turn_index']} | {m['doc_id']} | {m['doc_type']} | {txt} |"
        )

    lines += [
        "",
        "## Per-turn recall@k",
        "",
        "| Config | Query | Turn | k | Recall@k | Success | Failure category |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for t in turns:
        r_str = "n/a" if t["recall_at_k"] is None else f"{t['recall_at_k']:.2f}"
        fc = t["failure_category"] or "-"
        lines.append(
            f"| {t['configuration']} | {t['query_id']} | {t['turn_index']} | {t['k']} | {r_str} | {t['success']} | {fc} |"
        )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path, help="One or more run folders")
    a = ap.parse_args(argv)

    for run_dir in a.runs:
        analysis = analyze_run(run_dir)
        md = format_retrieval_md(analysis)
        out = run_dir / "retrieval.md"
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
