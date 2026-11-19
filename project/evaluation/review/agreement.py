"""Compute raw agreement and Cohen's kappa between human labels and scorer verdicts.

    cd project
    python evaluation/review/agreement.py --blind evaluation/review/scorer_audit_blind.csv --key evaluation/review/scorer_audit_key.csv
    python evaluation/review/agreement.py --blind evaluation/review/safety_review_blind.csv --key evaluation/review/safety_review_key.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any


def parse_bool(val: str) -> bool | None:
    s = (val or "").strip().lower()
    if not s:
        return None
    if s in ("true", "1", "yes", "pass", "y", "t"):
        return True
    if s in ("false", "0", "no", "fail", "n", "f"):
        return False
    raise ValueError(f"Unrecognized boolean value: {val!r}")


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


def compute_blind_agreement(blind_csv: Path, key_csv: Path) -> dict[str, Any]:
    with open(key_csv, encoding="utf-8") as f:
        keys = {r["sample_id"]: r for r in csv.DictReader(f)}
    with open(blind_csv, encoding="utf-8") as f:
        blinds = list(csv.DictReader(f))

    judged: list[tuple[str, bool, bool]] = []
    for b in blinds:
        h = parse_bool(b.get("human_success", ""))
        if h is None:
            continue
        k = keys.get(b["sample_id"])
        if k is None:
            raise KeyError(f"sample_id {b['sample_id']} missing from {key_csv}")
        a = parse_bool(k["scorer_success"])
        assert a is not None
        judged.append((k["configuration"], a, h))

    def _stats(items: list[tuple[str, bool, bool]]) -> dict[str, Any]:
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

    configs = sorted({cfg for cfg, _, _ in judged})
    return {
        "overall": _stats(judged),
        "per_config": {c: _stats([x for x in judged if x[0] == c]) for c in configs},
    }


def format_report(rep: dict[str, Any]) -> str:
    ov = rep["overall"]
    if ov["n"] == 0:
        return "No judged rows found (human_success is blank for all rows)."
    lines = [
        f"Overall agreement: {ov['agree']}/{ov['n']} ({ov['agreement_pct']:.1f}%), Cohen's kappa = {ov['kappa']:.3f}",
        "",
        "| Config | N | Agree | Agreement % | Cohen's kappa |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cfg, s in rep["per_config"].items():
        lines.append(f"| {cfg} | {s['n']} | {s['agree']} | {s['agreement_pct']:.1f}% | {s['kappa']:.3f} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind", type=Path, required=True)
    ap.add_argument("--key", type=Path, required=True)
    a = ap.parse_args(argv)
    print(format_report(compute_blind_agreement(a.blind, a.key)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
