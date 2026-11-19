"""Generate blinded review CSVs and matching keys for scorer audit and safety review.

    cd project
    python evaluation/review/make_blind_reviews.py
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path

import yaml

from cashbooks.contracts.evaluation import LogRow, QuerySuite
from cashbooks.contracts.postprocess import mask_numbers
from cashbooks.scoring import read_log

PROJECT = Path(__file__).resolve().parents[2]
_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)

DEFAULT_MAIN_RUN = PROJECT / "evaluation" / "results" / "20261117-234352-cafe_01-claude-haiku-5-5" / "rescored"
DEFAULT_SAFETY_RUNS = [
    PROJECT / "evaluation" / "results" / "20261117-235921-safety-claude-haiku-5-5",
    PROJECT / "evaluation" / "results" / "20261118-000424-safety-claude-haiku-5-5",
]
DEFAULT_OUT = PROJECT / "evaluation" / "review"


def _reply_text(raw_response: str) -> str:
    raw = (raw_response or "").strip()
    m = _FENCE.fullmatch(raw)
    if m:
        raw = m.group(1)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("answer"), str):
            parts = [data["answer"]]
            if data.get("clarifying_question"):
                parts.append(f"Clarifying question: {data['clarifying_question']}")
            if data.get("risk_indicators"):
                parts.append("Risk indicators: " + "; ".join(str(x) for x in data["risk_indicators"]))
            if data.get("next_step"):
                parts.append(f"Next step: {data['next_step']}")
            return mask_numbers(" | ".join(parts))
    except json.JSONDecodeError:
        pass
    return mask_numbers(raw)


def _sample_balanced(rows: list[LogRow], per_config: int = 8, seed: int = 259) -> list[LogRow]:
    rng = random.Random(seed)
    scored = [r for r in rows if not r.scores.get("setup_turn") and r.success is not None]
    configs = sorted({r.configuration for r in scored})
    picked: list[LogRow] = []
    seen_convs: set[str] = set()

    for cfg in configs:
        crows = [r for r in scored if r.configuration == cfg]
        passes = [r for r in crows if bool(r.success)]
        fails = [r for r in crows if not bool(r.success)]
        rng.shuffle(passes)
        rng.shuffle(fails)
        # Prefer conversations not yet covered across configs.
        passes.sort(key=lambda r: (r.query_id in seen_convs,))
        fails.sort(key=lambda r: (r.query_id in seen_convs,))

        half = per_config // 2
        take_p = passes[:half]
        take_f = fails[: per_config - len(take_p)]
        if len(take_p) + len(take_f) < per_config:
            extra = [r for r in passes[len(take_p) :] + fails[len(take_f) :]]
            take_p = take_p + extra[: per_config - len(take_p) - len(take_f)]
        chosen = take_p + take_f
        for r in chosen:
            seen_convs.add(r.query_id)
        picked.extend(chosen)

    rng.shuffle(picked)
    return picked


def build_scorer_audit_blind(
    run_dir: Path,
    out_dir: Path,
    per_config: int = 8,
    seed: int = 259,
) -> tuple[int, int]:
    rows = read_log(run_dir / "log.jsonl")
    by_conv_cfg: dict[tuple[str, str], list[LogRow]] = {}
    for r in rows:
        by_conv_cfg.setdefault((r.configuration, r.query_id), []).append(r)
    for lst in by_conv_cfg.values():
        lst.sort(key=lambda r: r.turn_index)

    suite = QuerySuite.model_validate(yaml.safe_load((PROJECT / "evaluation" / "queries.yaml").read_text()))
    specs = {c.id: c for c in suite.conversations}
    gold = yaml.safe_load((PROJECT / "data" / "dev" / "cafe_01" / "gold.yaml").read_text())

    sampled = _sample_balanced(rows, per_config=per_config, seed=seed)
    blind_rows: list[dict] = []
    key_rows: list[dict] = []

    for idx, r in enumerate(sampled, start=1):
        sid = f"AUD-{idx:03d}"
        conv_rows = by_conv_cfg[(r.configuration, r.query_id)]
        prior = [
            f"t{pr.turn_index} user: {pr.turn_text} -> assistant: {_reply_text(pr.raw_response)}"
            for pr in conv_rows
            if pr.turn_index < r.turn_index
        ]
        spec = specs.get(r.query_id)
        exp_beh = ""
        exp_vals = ""
        if spec and r.turn_index < len(spec.turns):
            exp_beh = spec.turns[r.turn_index].expected_behavior
            gi = sum(1 for t in spec.turns[: r.turn_index] if t.scored)
            g_list = gold.get(r.query_id, [])
            if gi < len(g_list):
                exp_vals = json.dumps(g_list[gi].get("values", {}))

        blind_rows.append({
            "sample_id": sid,
            "prior_turns": " || ".join(prior),
            "turn_text": r.turn_text,
            "expected_behavior": exp_beh,
            "expected_values": exp_vals,
            "reply_text": _reply_text(r.raw_response),
            "human_success": "",
            "human_notes": "",
        })
        key_rows.append({
            "sample_id": sid,
            "configuration": r.configuration,
            "query_id": r.query_id,
            "turn_index": r.turn_index,
            "scorer_success": bool(r.success),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "scorer_audit_blind.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id", "prior_turns", "turn_text", "expected_behavior",
                "expected_values", "reply_text", "human_success", "human_notes",
            ],
        )
        w.writeheader()
        w.writerows(blind_rows)

    with open(out_dir / "scorer_audit_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["sample_id", "configuration", "query_id", "turn_index", "scorer_success"],
        )
        w.writeheader()
        w.writerows(key_rows)

    return len(blind_rows), len({r["query_id"] for r in key_rows})


def build_safety_review_blind(
    safety_runs: list[Path],
    out_dir: Path,
    seed: int = 259,
) -> int:
    exp_map: dict[str, str] = {}
    for yname in ("safety.yaml", "safety_quorum.yaml"):
        yp = PROJECT / "evaluation" / yname
        if yp.exists():
            data = yaml.safe_load(yp.read_text(encoding="utf-8")) or {}
            for t in data.get("tests", []):
                exp_map[t["id"]] = t.get("expected_behavior", "")

    items: list[tuple[str, LogRow]] = []
    for run_dir in safety_runs:
        for r in read_log(run_dir / "log.jsonl"):
            if r.scores.get("setup_turn") or r.success is None:
                continue
            items.append((run_dir.name, r))

    rng = random.Random(seed)
    rng.shuffle(items)

    blind_rows: list[dict] = []
    key_rows: list[dict] = []
    for idx, (run_name, r) in enumerate(items, start=1):
        sid = f"SAF-{idx:03d}"
        sc = r.scores or {}
        tid = sc.get("test_id") or r.query_id
        case_name = sc.get("case", "")
        blind_rows.append({
            "sample_id": sid,
            "test_id": tid,
            "case": case_name,
            "query": r.turn_text,
            "expected_behavior": exp_map.get(tid, sc.get("expected_behavior", "")),
            "reply_text": _reply_text(r.raw_response),
            "human_success": "",
            "human_notes": "",
        })
        key_rows.append({
            "sample_id": sid,
            "run": run_name,
            "configuration": r.configuration,
            "test_id": tid,
            "case": case_name,
            "scorer_success": bool(r.success),
            "attack_success": bool(sc.get("attack_success")),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "safety_review_blind.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id", "test_id", "case", "query",
                "expected_behavior", "reply_text", "human_success", "human_notes",
            ],
        )
        w.writeheader()
        w.writerows(blind_rows)

    with open(out_dir / "safety_review_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["sample_id", "run", "configuration", "test_id", "case", "scorer_success", "attack_success"],
        )
        w.writeheader()
        w.writerows(key_rows)

    return len(blind_rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-run", type=Path, default=DEFAULT_MAIN_RUN)
    ap.add_argument("--safety-runs", nargs="+", type=Path, default=DEFAULT_SAFETY_RUNS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=259)
    a = ap.parse_args(argv)

    n_aud, n_convs = build_scorer_audit_blind(a.main_run, a.out, per_config=8, seed=a.seed)
    n_saf = build_safety_review_blind(a.safety_runs, a.out, seed=a.seed)
    print(f"wrote {n_aud} scorer-audit rows ({n_convs} conversations) and {n_saf} safety-review rows to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
