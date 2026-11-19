"""Stratified scorer-audit sampling and human-agreement reporting.

Sample 40 scored turns (stratified by configuration and automatic success):
    cd project
    python evaluation/audit_sample.py sample evaluation/results/<run_id>

Report agreement after filling human_success in evaluation/scorer_audit.csv:
    python evaluation/audit_sample.py report --csv evaluation/scorer_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.evaluation import LogRow, QuerySuite
from cashbooks.contracts.postprocess import mask_numbers
from cashbooks.scoring import read_log

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT / "evaluation" / "scorer_audit.csv"
DEFAULT_QUERIES = PROJECT / "evaluation" / "queries.yaml"
_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)

CSV_FIELDS = [
    "run",
    "config",
    "query_id",
    "turn",
    "question",
    "expected_behavior",
    "reply",
    "automatic_success",
    "automatic_reasons",
    "human_success",
    "human_note",
]


def _reply_text(raw_response: str) -> str:
    raw = (raw_response or "").strip()
    m = _FENCE.fullmatch(raw)
    if m:
        raw = m.group(1)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("answer"), str):
            return mask_numbers(data["answer"])
    except json.JSONDecodeError:
        pass
    return mask_numbers(raw)


def _auto_reasons(row: LogRow) -> str:
    sc = row.scores or {}
    parts: list[str] = []
    if not row.parsed_ok:
        parts.append("unparsed")
    else:
        if not sc.get("answerability_ok", True):
            parts.append(f"answerability_mismatch(expected={row.expected.value})")
        vals = sc.get("values") or {}
        bad_vals = [k for k, ok in vals.items() if not ok]
        if bad_vals:
            parts.append(f"wrong_values={bad_vals}")
        rec = sc.get("evidence_recall")
        if rec is not None and rec == 0:
            parts.append("evidence_recall=0")
        hits = sc.get("must_not_hits") or []
        if hits:
            parts.append(f"must_not={hits}")
    if row.notes:
        parts.append(row.notes)
    return mask_numbers("; ".join(parts) if parts else "all_checks_passed")


def stratified_sample(rows: list[LogRow], n: int = 40, seed: int = 42) -> list[LogRow]:
    """Pick n scored turns stratified by configuration and automatic success (half pass, half fail)."""
    scored = [r for r in rows if not r.scores.get("setup_turn") and r.success is not None]
    if len(scored) <= n:
        return sorted(scored, key=lambda r: (r.configuration, r.query_id, r.turn_index))

    rng = random.Random(seed)
    configs = sorted({r.configuration for r in scored})
    buckets: dict[tuple[str, bool], list[LogRow]] = {}
    for c in configs:
        for ok in (True, False):
            items = [r for r in scored if r.configuration == c and bool(r.success) is ok]
            rng.shuffle(items)
            buckets[(c, ok)] = items

    per_bucket = n // (len(configs) * 2) if configs else 0
    picked: list[LogRow] = []
    picked_keys: set[tuple[str, str, int]] = set()

    for key in sorted(buckets):
        take = buckets[key][:per_bucket]
        for r in take:
            picked.append(r)
            picked_keys.add((r.configuration, r.query_id, r.turn_index))

    if len(picked) < n:
        # Top up evenly from remaining items across buckets, preserving half/half balance where possible.
        remaining = [r for r in scored if (r.configuration, r.query_id, r.turn_index) not in picked_keys]
        rng.shuffle(remaining)
        for r in remaining[: n - len(picked)]:
            picked.append(r)

    return sorted(picked, key=lambda r: (r.configuration, r.query_id, r.turn_index))


def write_audit_csv(
    run_dir: Path,
    out_csv: Path = DEFAULT_CSV,
    n: int = 40,
    seed: int = 42,
    queries_path: Path = DEFAULT_QUERIES,
) -> list[dict[str, Any]]:
    rows = read_log(run_dir / "log.jsonl")
    suite = QuerySuite.model_validate(yaml.safe_load(queries_path.read_text(encoding="utf-8")))
    specs = {c.id: c for c in suite.conversations}

    sampled = stratified_sample(rows, n=n, seed=seed)
    records: list[dict[str, Any]] = []
    for r in sampled:
        exp_beh = ""
        if r.query_id in specs and r.turn_index < len(specs[r.query_id].turns):
            exp_beh = specs[r.query_id].turns[r.turn_index].expected_behavior
        records.append({
            "run": run_dir.name,
            "config": r.configuration,
            "query_id": r.query_id,
            "turn": r.turn_index,
            "question": r.turn_text,
            "expected_behavior": exp_beh,
            "reply": _reply_text(r.raw_response),
            "automatic_success": bool(r.success),
            "automatic_reasons": _auto_reasons(r),
            "human_success": "",
            "human_note": "",
        })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for rec in records:
            w.writerow(rec)
    return records


def _parse_bool(val: str) -> bool | None:
    s = (val or "").strip().lower()
    if not s:
        return None
    if s in ("true", "1", "yes", "pass", "y", "t"):
        return True
    if s in ("false", "0", "no", "fail", "n", "f"):
        return False
    raise ValueError(f"Unrecognized boolean value in audit CSV: {val!r}")


def cohens_kappa(auto: list[bool], human: list[bool]) -> float:
    n = len(auto)
    if n == 0:
        return 0.0
    po = sum(1 for a, h in zip(auto, human) if a == h) / n
    p_a1 = sum(1 for a in auto if a) / n
    p_h1 = sum(1 for h in human if h) / n
    pe = (p_a1 * p_h1) + ((1 - p_a1) * (1 - p_h1))
    if abs(1.0 - pe) < 1e-12:
        return 1.0 if abs(po - 1.0) < 1e-12 else 0.0
    return (po - pe) / (1.0 - pe)


def compute_agreement(csv_path: Path = DEFAULT_CSV) -> dict[str, Any]:
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    judged: list[tuple[dict[str, str], bool, bool]] = []
    for r in rows:
        h = _parse_bool(r.get("human_success", ""))
        a = _parse_bool(r.get("automatic_success", ""))
        if h is None or a is None:
            continue
        judged.append((r, a, h))

    def _stats(items: list[tuple[dict[str, str], bool, bool]]) -> dict[str, Any]:
        n = len(items)
        if n == 0:
            return {"n": 0, "agree": 0, "agreement_pct": None, "kappa": None}
        auto = [a for _, a, _ in items]
        human = [h for _, _, h in items]
        agree = sum(1 for a, h in zip(auto, human) if a == h)
        return {
            "n": n,
            "agree": agree,
            "agreement_pct": round(100.0 * agree / n, 1),
            "kappa": round(cohens_kappa(auto, human), 3),
        }

    configs = sorted({r["config"] for r, _, _ in judged})
    per_config = {c: _stats([(r, a, h) for r, a, h in judged if r["config"] == c]) for c in configs}
    disagreements = [
        {
            "config": r["config"],
            "query_id": r["query_id"],
            "turn": r["turn"],
            "automatic_success": a,
            "human_success": h,
            "human_note": r.get("human_note", ""),
            "automatic_reasons": r.get("automatic_reasons", ""),
        }
        for r, a, h in judged
        if a != h
    ]
    return {
        "overall": _stats(judged),
        "per_config": per_config,
        "disagreements": disagreements,
    }


def format_agreement_report(rep: dict[str, Any]) -> str:
    ov = rep["overall"]
    if ov["n"] == 0:
        return "No judged rows found (human_success is blank for all rows)."
    lines = [
        f"Overall agreement: {ov['agree']}/{ov['n']} ({ov['agreement_pct']:.1f}%), Cohen's kappa = {ov['kappa']:.3f}",
        "",
        "| Config | N | Agree | Agreement % | Cohen's kappa |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c, s in rep["per_config"].items():
        lines.append(f"| {c} | {s['n']} | {s['agree']} | {s['agreement_pct']:.1f}% | {s['kappa']:.3f} |")
    lines.append("")
    if rep["disagreements"]:
        lines.append(f"Disagreements ({len(rep['disagreements'])}):")
        for d in rep["disagreements"]:
            lines.append(
                f"- {d['config']} {d['query_id']} t{d['turn']}: auto={d['automatic_success']} "
                f"human={d['human_success']} | reasons={d['automatic_reasons']} | note={d['human_note']}"
            )
    else:
        lines.append("Disagreements: none.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)

    sp = sub.add_parser("sample", help="Sample scored turns into scorer_audit.csv")
    sp.add_argument("run", type=Path, help="Run directory containing log.jsonl")
    sp.add_argument("--out", type=Path, default=DEFAULT_CSV)
    sp.add_argument("--n", type=int, default=40)
    sp.add_argument("--seed", type=int, default=42)
    sp.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)

    rp = sub.add_parser("report", help="Compute agreement and Cohen's kappa from filled CSV")
    rp.add_argument("--csv", type=Path, default=DEFAULT_CSV)

    a = ap.parse_args()
    if a.mode == "sample":
        recs = write_audit_csv(a.run, out_csv=a.out, n=a.n, seed=a.seed, queries_path=a.queries)
        print(f"wrote {len(recs)} rows to {a.out}")
        return 0
    rep = compute_agreement(a.csv)
    print(format_agreement_report(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
