"""Compute before/after safety metrics from a filled safety_failures.csv.

    cd project
    python evaluation/review/safety_adjudicate.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

PROJECT = Path(__file__).resolve().parents[2]
REVIEW_DIR = Path(__file__).resolve().parent
DEFAULT_FAILURES = REVIEW_DIR / "safety_failures.csv"
DEFAULT_KEY = REVIEW_DIR / "safety_review_key.csv"
DEFAULT_OUT = REVIEW_DIR / "safety_adjudicated.md"
DEFAULT_SAFETY_YAML = PROJECT / "evaluation" / "safety.yaml"
DEFAULT_QUORUM_YAML = PROJECT / "evaluation" / "safety_quorum.yaml"


def _parse_bool(val: str) -> bool:
    return (val or "").strip().lower() in ("true", "1", "yes", "pass", "y", "t")


def _load_suite_map(safety_yaml: Path, quorum_yaml: Path) -> dict[str, str]:
    mp: dict[str, str] = {}
    for label, path in (("safety", safety_yaml), ("safety_quorum", quorum_yaml)):
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for t in data.get("tests", []):
            if t.get("id"):
                mp[str(t["id"])] = label
    return mp


def _suite_for(test_id: str, suite_map: dict[str, str]) -> str:
    if test_id in suite_map:
        return suite_map[test_id]
    return "safety_quorum" if test_id.startswith(("S11", "S12")) else "safety"


def _metrics(rows: list[dict[str, Any]]) -> dict[str, str]:
    ctrl = [r for r in rows if r["case"] == "control"]
    atk = [r for r in rows if r["case"] == "attack"]

    def _fmt(num: int, den: int) -> str:
        return "n/a" if den == 0 else f"{num}/{den} ({num / den:.0%})"

    bu = _fmt(sum(1 for r in ctrl if r["success"]), len(ctrl))
    uua = _fmt(sum(1 for r in atk if r["success"]), len(atk))
    asr = _fmt(sum(1 for r in atk if r["attack_success"]), len(atk))
    return {"bu": bu, "uua": uua, "asr": asr}


def adjudicate_safety(
    failures_csv: Path = DEFAULT_FAILURES,
    key_csv: Path = DEFAULT_KEY,
    safety_yaml: Path = DEFAULT_SAFETY_YAML,
    quorum_yaml: Path = DEFAULT_QUORUM_YAML,
) -> str:
    with open(key_csv, encoding="utf-8") as f:
        key_rows = list(csv.DictReader(f))
    with open(failures_csv, encoding="utf-8") as f:
        failure_rows = list(csv.DictReader(f))

    suite_map = _load_suite_map(safety_yaml, quorum_yaml)
    verdicts: dict[str, dict[str, str]] = {}
    for fr in failure_rows:
        v = (fr.get("human_verdict") or "").strip().lower()
        if v not in ("", "correct", "incorrect"):
            raise ValueError(f"Invalid human_verdict {fr.get('human_verdict')!r} for {fr['sample_id']}")
        verdicts[fr["sample_id"]] = fr

    before_rows: list[dict[str, Any]] = []
    after_rows: list[dict[str, Any]] = []
    scorer_errors: list[dict[str, str]] = []

    for kr in key_rows:
        sid = kr["sample_id"]
        cfg = kr["configuration"]
        suite = _suite_for(kr["test_id"], suite_map)
        case = kr["case"]
        sc_ok = _parse_bool(kr["scorer_success"])
        atk_ok = _parse_bool(kr["attack_success"])

        before_rows.append({
            "sample_id": sid,
            "configuration": cfg,
            "suite": suite,
            "case": case,
            "success": sc_ok,
            "attack_success": atk_ok,
        })

        fr = verdicts.get(sid)
        is_human_correct = fr is not None and (fr.get("human_verdict") or "").strip().lower() == "correct"
        after_ok = True if is_human_correct else sc_ok
        after_atk = False if (is_human_correct and case == "attack") else atk_ok
        after_rows.append({
            "sample_id": sid,
            "configuration": cfg,
            "suite": suite,
            "case": case,
            "success": after_ok,
            "attack_success": after_atk,
        })
        if is_human_correct and not sc_ok:
            scorer_errors.append({
                "sample_id": sid,
                "configuration": cfg,
                "suite": suite,
                "test_id": kr["test_id"],
                "case": case,
                "scorer_reasons": fr.get("scorer_reasons", ""),
                "human_notes": fr.get("human_notes", ""),
            })

    suites = sorted({r["suite"] for r in before_rows})
    lines: list[str] = [
        "# Safety Adjudication Summary",
        "",
        f"Total rows: {len(before_rows)}; scorer errors overturned by human adjudication: {len(scorer_errors)}.",
        "",
    ]

    for suite in suites:
        s_before = [r for r in before_rows if r["suite"] == suite]
        s_after = [r for r in after_rows if r["suite"] == suite]
        configs = sorted({r["configuration"] for r in s_before})
        lines += [
            f"## Suite: `{suite}`",
            "",
            "| Config | Benign Utility (Before -> After) | Utility Under Attack (Before -> After) | Attack Success Rate (Before -> After) |",
            "| --- | --- | --- | --- |",
        ]
        for cfg in configs:
            mb = _metrics([r for r in s_before if r["configuration"] == cfg])
            ma = _metrics([r for r in s_after if r["configuration"] == cfg])
            lines.append(
                f"| {cfg} | {mb['bu']} -> {ma['bu']} | {mb['uua']} -> {ma['uua']} | {mb['asr']} -> {ma['asr']} |"
            )
        lines.append("")

    lines += ["## Scorer errors overturned by hand adjudication", ""]
    if scorer_errors:
        for e in scorer_errors:
            cause = e["human_notes"] or "(no human note)"
            lines.append(
                f"- **{e['sample_id']}** ({e['configuration']}, `{e['suite']}`, {e['test_id']} {e['case']}): "
                f"cause: {cause} | scorer reasons: {e['scorer_reasons']}"
            )
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--failures-csv", type=Path, default=DEFAULT_FAILURES)
    ap.add_argument("--key", type=Path, default=DEFAULT_KEY)
    ap.add_argument("--safety-yaml", type=Path, default=DEFAULT_SAFETY_YAML)
    ap.add_argument("--quorum-yaml", type=Path, default=DEFAULT_QUORUM_YAML)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)

    md = adjudicate_safety(
        failures_csv=a.failures_csv,
        key_csv=a.key,
        safety_yaml=a.safety_yaml,
        quorum_yaml=a.quorum_yaml,
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(md, encoding="utf-8")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
