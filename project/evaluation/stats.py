"""Paired statistical comparisons and sample-size planning over evaluation runs.

    cd project
    python evaluation/stats.py evaluation/results/<run>/rescored
    python evaluation/stats.py evaluation/results/<run>/rescored --plan 28 60 90

Writes stats.md into the first run folder.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from collections.abc import Hashable
from pathlib import Path
from typing import Any

from cashbooks.contracts.evaluation import LogRow
from cashbooks.scoring import read_log


def exact_mcnemar_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from discordant counts b (A only) and c (B only)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def _scored_turns_by_run(run_dirs: list[Path]) -> list[dict[tuple[str, str, str, int], float]]:
    per_run: list[dict[tuple[str, str, str, int], float]] = []
    for d in run_dirs:
        rows: list[LogRow] = read_log(d / "log.jsonl")
        mp: dict[tuple[str, str, str, int], float] = {}
        for r in rows:
            if r.scores.get("setup_turn") or r.success is None:
                continue
            mp[(r.configuration, r.scenario, r.query_id, r.turn_index)] = 1.0 if r.success else 0.0
        per_run.append(mp)
    return per_run


def describe_run_grouping(run_dirs: list[Path]) -> dict[str, list[str]]:
    """Map each scenario name to the list of run labels covering it."""
    by_scenario: dict[str, list[str]] = defaultdict(list)
    for d in run_dirs:
        label = d.parent.name if d.name == "rescored" else d.name
        rows = read_log(d / "log.jsonl")
        scenarios = sorted({r.scenario for r in rows if not r.scores.get("setup_turn") and r.success is not None})
        for sc in scenarios:
            by_scenario[sc].append(label)
    return dict(sorted(by_scenario.items()))


def format_run_grouping(by_scenario: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    for sc, labels in by_scenario.items():
        role = "repeats" if len(labels) > 1 else "single run"
        lines.append(f"- Scenario `{sc}` ({role}, {len(labels)} run(s)): {', '.join(labels)}")
    return lines


def bootstrap_diff_ci(
    conv_turns_a: dict[Any, list[float]],
    conv_turns_b: dict[Any, list[float]],
    conv_ids: list[Any],
    resamples: int = 10000,
    seed: int = 259,
) -> tuple[float, float, float]:
    """Return (observed_diff, ci_low, ci_high) resampling whole (scenario, query_id) clusters."""
    def _rate(ids: list[Any], mp: dict[Any, list[float]]) -> float:
        vals = [v for q in ids for v in mp[q]]
        return sum(vals) / len(vals) if vals else 0.0

    obs = _rate(conv_ids, conv_turns_a) - _rate(conv_ids, conv_turns_b)
    rng = random.Random(seed)
    diffs: list[float] = []
    k = len(conv_ids)
    for _ in range(resamples):
        sample = rng.choices(conv_ids, k=k)
        diffs.append(_rate(sample, conv_turns_a) - _rate(sample, conv_turns_b))
    diffs.sort()
    lo = diffs[max(0, int(0.025 * resamples))]
    hi = diffs[min(resamples - 1, int(0.975 * resamples))]
    return obs, lo, hi


def pairwise_stats(
    run_dirs: list[Path],
    resamples: int = 10000,
    seed: int = 259,
) -> tuple[list[str], list[dict], float]:
    """Compute pairwise McNemar and cluster-bootstrap CIs across one or more runs."""
    per_run = _scored_turns_by_run(run_dirs)
    configs = sorted({c for mp in per_run for (c, _, _, _) in mp})
    turn_keys = sorted({(sc, q, t) for mp in per_run for (_, sc, q, t) in mp})
    conv_ids = sorted({(sc, q) for sc, q, _ in turn_keys})

    # Mean success per (config, scenario, query_id, turn_index) across repeat runs of the same scenario
    mean_scores: dict[str, dict[tuple[str, str], list[float]]] = {c: defaultdict(list) for c in configs}
    for c in configs:
        for sc, q, t in turn_keys:
            vals = [mp[(c, sc, q, t)] for mp in per_run if (c, sc, q, t) in mp]
            if vals:
                mean_scores[c][(sc, q)].append(sum(vals) / len(vals))

    results: list[dict] = []
    disc_rates: list[float] = []
    for i, a in enumerate(configs):
        for b_cfg in configs[i + 1 :]:
            b_cnt = 0
            c_cnt = 0
            total_pairs = 0
            for mp in per_run:
                for sc, q, t in turn_keys:
                    if (a, sc, q, t) in mp and (b_cfg, sc, q, t) in mp:
                        total_pairs += 1
                        sa = mp[(a, sc, q, t)] >= 0.5
                        sb = mp[(b_cfg, sc, q, t)] >= 0.5
                        if sa and not sb:
                            b_cnt += 1
                        elif sb and not sa:
                            c_cnt += 1
            p_val = exact_mcnemar_p(b_cnt, c_cnt)
            diff, lo, hi = bootstrap_diff_ci(mean_scores[a], mean_scores[b_cfg], conv_ids, resamples, seed)
            if total_pairs:
                disc_rates.append((b_cnt + c_cnt) / total_pairs)
            results.append({
                "a": a,
                "b": b_cfg,
                "b_only": b_cnt,
                "c_only": c_cnt,
                "p_value": p_val,
                "diff": diff,
                "ci_low": lo,
                "ci_high": hi,
            })

    disc_sorted = sorted(disc_rates)
    median_disc = disc_sorted[len(disc_sorted) // 2] if disc_sorted else 0.0
    return configs, results, median_disc


def estimate_mde(
    n_turns: int,
    discordance_rate: float,
    power_target: float = 0.80,
    alpha: float = 0.05,
    trials: int = 2000,
    seed: int = 259,
) -> float | None:
    """Estimate smallest success-rate difference detectable at 80% power (exact McNemar)."""
    if discordance_rate <= 0 or n_turns <= 0:
        return None
    rng = random.Random(seed + n_turns)
    step = 0.01
    delta = step
    while delta <= discordance_rate + 1e-9:
        p10 = (discordance_rate + delta) / 2.0
        p01 = (discordance_rate - delta) / 2.0
        rejects = 0
        for _ in range(trials):
            b = 0
            c = 0
            for _ in range(n_turns):
                u = rng.random()
                if u < p10:
                    b += 1
                elif u < p10 + p01:
                    c += 1
            if exact_mcnemar_p(b, c) < alpha:
                rejects += 1
        if rejects / trials >= power_target:
            return round(delta, 2)
        delta += step
    return None


def format_stats_md(
    run_dirs: list[Path],
    results: list[dict],
    median_disc: float,
    plan_ns: list[int],
    resamples: int,
    seed: int,
    grouping: dict[str, list[str]] | None = None,
) -> str:
    lines = [
        f"# Paired Statistics ({run_dirs[0].parent.name if run_dirs[0].name == 'rescored' else run_dirs[0].name})",
        "",
        f"Runs: {len(run_dirs)}; bootstrap resamples: {resamples} (seed {seed}, `(scenario, query_id)` clusters).",
        "",
    ]
    if grouping:
        lines.extend(format_run_grouping(grouping))
        lines.append("")
    lines += [
        "| Pair (A vs B) | Discordant (A:B) | Exact McNemar p | Diff (A - B) | 95% Bootstrap CI |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r['a']} vs {r['b']} | {r['b_only']}:{r['c_only']} | {r['p_value']:.3f} | "
            f"{r['diff']:+.1%} | [{r['ci_low']:+.1%}, {r['ci_high']:+.1%}] |"
        )
    if plan_ns:
        lines += [
            "",
            f"## Power planning (observed median discordance rate {median_disc:.1%}, alpha = 0.05, power = 80%)",
            "",
            "| N turns | Minimum detectable difference |",
            "| --- | --- |",
        ]
        for n in plan_ns:
            mde = estimate_mde(n, median_disc)
            lines.append(f"| {n} | {'not achievable' if mde is None else f'{mde:.0%}'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path, help="One or more run folders containing log.jsonl")
    ap.add_argument("--plan", nargs="*", type=int, default=[], help="Sample sizes N for MDE simulation")
    ap.add_argument("--resamples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=259)
    a = ap.parse_args(argv)

    grouping = describe_run_grouping(a.runs)
    _, results, median_disc = pairwise_stats(a.runs, resamples=a.resamples, seed=a.seed)
    md = format_stats_md(a.runs, results, median_disc, a.plan, a.resamples, a.seed, grouping=grouping)
    out = a.runs[0] / "stats.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
