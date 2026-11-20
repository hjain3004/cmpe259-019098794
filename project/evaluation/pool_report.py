"""Pool evaluation runs across repeats and scenarios into a single report.md.

    cd project
    python evaluation/pool_report.py evaluation/results/<run1> evaluation/results/<run2> ... --out evaluation/results/pooled-20261118
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from cashbooks.contracts.evaluation import LogRow
from cashbooks.scoring import (
    _load_query_labels,
    conversation_success,
    read_log,
    summarize,
    summarize_by_label,
)

EVAL_DIR = Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from lecture_metrics import _load_gold_evidence_counts, compute_citation_f1  # noqa: E402
from stats import describe_run_grouping, estimate_mde, format_run_grouping, pairwise_stats  # noqa: E402


def resolve_run_dir(run_dir: Path) -> Path:
    """Prefer <run>/rescored when it exists and contains log.jsonl."""
    if run_dir.name != "rescored" and (run_dir / "rescored" / "log.jsonl").exists():
        return run_dir / "rescored"
    return run_dir


def _scored_rows(run_dir: Path) -> list[LogRow]:
    return [
        r for r in read_log(run_dir / "log.jsonl")
        if not r.scores.get("setup_turn") and r.success is not None
    ]


def _conv_counts(rows: list[LogRow]) -> dict[str, tuple[int, int]]:
    conv = conversation_success(rows)
    return {c: (sum(per.values()), len(per)) for c, per in conv.items()}


def build_pool_report(
    run_dirs: list[Path],
    plan_ns: list[int] | None = None,
    resamples: int = 10000,
    seed: int = 259,
    query_labels: dict[str, list[str]] | None = None,
) -> str:
    resolved = [resolve_run_dir(d) for d in run_dirs]
    grouping = describe_run_grouping(resolved)

    per_run_rows: list[tuple[Path, str, list[LogRow]]] = []
    all_rows: list[LogRow] = []
    by_scenario_rows: dict[str, list[LogRow]] = defaultdict(list)
    by_scenario_convs: dict[str, dict[str, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    by_scenario_run_rates: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for d in resolved:
        rows = _scored_rows(d)
        all_rows.extend(rows)
        scenarios = sorted({r.scenario for r in rows})
        sc_label = scenarios[0] if len(scenarios) == 1 else "+".join(scenarios)
        per_run_rows.append((d, sc_label, rows))
        for sc in scenarios:
            sc_rows = [r for r in rows if r.scenario == sc]
            by_scenario_rows[sc].extend(sc_rows)
            sc_summary = summarize(sc_rows)
            sc_convs = _conv_counts(sc_rows)
            for cname, s in sc_summary.items():
                by_scenario_run_rates[sc][cname].append(s["success_rate"])
                if cname in sc_convs:
                    by_scenario_convs[sc][cname].append(sc_convs[cname])

    pooled_summary = summarize(all_rows)
    configs = list(pooled_summary.keys())
    scenarios = sorted(by_scenario_rows.keys())
    pooled_convs: dict[str, tuple[int, int]] = {}
    for c in configs:
        ok = sum(x for sc in scenarios for x, _ in by_scenario_convs[sc].get(c, []))
        tot = sum(y for sc in scenarios for _, y in by_scenario_convs[sc].get(c, []))
        pooled_convs[c] = (ok, tot)

    lines: list[str] = [
        "# Pooled Evaluation Report",
        "",
        f"Runs pooled: {len(resolved)} across {len(scenarios)} scenario(s).",
        "",
        *format_run_grouping(grouping),
        "",
        "## Turn and conversation success",
        "",
        "| Scope | Config | Turn success | Conversation success | Parse rate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for sc in scenarios:
        sc_sum = summarize(by_scenario_rows[sc])
        for c in configs:
            s = sc_sum.get(c)
            if not s:
                continue
            cok = sum(x for x, _ in by_scenario_convs[sc].get(c, []))
            ctot = sum(y for _, y in by_scenario_convs[sc].get(c, []))
            crate = f"{cok}/{ctot} ({cok / ctot:.0%})" if ctot else "n/a"
            prate = f"{s['parsed']}/{s['turns']} ({s['parsed'] / s['turns']:.0%})" if s["turns"] else "n/a"
            lines.append(
                f"| {sc} | {c} | {s['successes']}/{s['turns']} ({s['success_rate']:.0%}) | {crate} | {prate} |"
            )
    for c in configs:
        s = pooled_summary[c]
        cok, ctot = pooled_convs[c]
        crate = f"{cok}/{ctot} ({cok / ctot:.0%})" if ctot else "n/a"
        prate = f"{s['parsed']}/{s['turns']} ({s['parsed'] / s['turns']:.0%})" if s["turns"] else "n/a"
        lines.append(
            f"| **Pooled** | **{c}** | **{s['successes']}/{s['turns']} ({s['success_rate']:.0%})** | "
            f"**{crate}** | **{prate}** |"
        )

    lines += [
        "",
        "## Run-to-run spread (min–max turn success across repeats)",
        "",
        "| Config | " + " | ".join(scenarios) + " |",
        "| --- |" + " --- |" * len(scenarios),
    ]
    for c in configs:
        cells = []
        for sc in scenarios:
            rates = by_scenario_run_rates[sc].get(c, [])
            if not rates:
                cells.append("n/a")
            elif len(rates) == 1:
                cells.append(f"{rates[0]:.0%}")
            else:
                cells.append(f"{min(rates):.0%}–{max(rates):.0%}")
        lines.append(f"| {c} | " + " | ".join(cells) + " |")

    cit_f1 = compute_citation_f1(all_rows, _load_gold_evidence_counts(resolved))
    lines += [
        "",
        "## Error rates and grounding (pooled)",
        "",
        "| Config | Unwarranted-warning rate | Over-abstention rate | Citation recall | Citation precision | Mean citation F1 | Micro citation F1 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in configs:
        s = pooled_summary[c]
        cf = cit_f1.get(c, {})
        uwr = s["unwarranted_warning_rate"]
        oar = s["over_abstention_rate"]
        mr = s["mean_evidence_recall"]
        mp = s["mean_evidence_precision"]
        mf1 = cf.get("mean_f1")
        uf1 = cf.get("micro_f1")
        uw_str = "n/a" if uwr is None else f"{s['unwarranted_warnings']}/{s['unwarranted_warning_eligible']} ({uwr:.0%})"
        oa_str = "n/a" if oar is None else f"{s['over_abstentions']}/{s['over_abstention_eligible']} ({oar:.0%})"
        lines.append(
            f"| {c} | {uw_str} | {oa_str} | "
            f"{'n/a' if mr is None else f'{mr:.3f}'} | {'n/a' if mp is None else f'{mp:.3f}'} | "
            f"{'n/a' if mf1 is None else f'{mf1:.3f}'} | {'n/a' if uf1 is None else f'{uf1:.3f}'} |"
        )

    qlabels = query_labels if query_labels is not None else _load_query_labels()
    if qlabels:
        by_label = summarize_by_label(all_rows, qlabels)
        lines += [
            "",
            "## Per-question-type turn success (pooled)",
            "",
            "| Label | " + " | ".join(configs) + " |",
            "| --- |" + " --- |" * len(configs),
        ]
        for lbl, per_cfg in by_label.items():
            cells = [f"{per_cfg[c]['correct']}/{per_cfg[c]['total']}" if c in per_cfg else "0/0" for c in configs]
            lines.append(f"| {lbl} | " + " | ".join(cells) + " |")

    _, results, median_disc = pairwise_stats(resolved, resamples=resamples, seed=seed)
    lines += [
        "",
        f"## Paired statistics (pooled turns, {resamples} bootstrap resamples, `(scenario, query_id)` clusters)",
        "",
        "| Pair (A vs B) | Discordant (A:B) | Exact McNemar p | Diff (A - B) | 95% Bootstrap CI |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r['a']} vs {r['b']} | {r['b_only']}:{r['c_only']} | {r['p_value']:.3f} | "
            f"{r['diff']:+.1%} | [{r['ci_low']:+.1%}, {r['ci_high']:+.1%}] |"
        )

    plan = plan_ns if plan_ns is not None else [60, 90, 120]
    if plan:
        lines += [
            "",
            f"### Power planning (observed median discordance rate {median_disc:.1%}, alpha = 0.05, power = 80%)",
            "",
            "| N turns | Minimum detectable difference |",
            "| --- | --- |",
        ]
        for n in plan:
            mde = estimate_mde(n, median_disc)
            lines.append(f"| {n} | {'not achievable' if mde is None else f'{mde:.0%}'} |")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path, help="Run folders (prefers <run>/rescored when present)")
    ap.add_argument("--out", type=Path, required=True, help="Output folder for report.md")
    ap.add_argument("--plan", nargs="*", type=int, default=[60, 90, 120])
    ap.add_argument("--resamples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=259)
    a = ap.parse_args(argv)

    resolved = [resolve_run_dir(d) for d in a.runs]
    grouping = describe_run_grouping(resolved)
    for line in format_run_grouping(grouping):
        print(line)

    md = build_pool_report(a.runs, plan_ns=a.plan, resamples=a.resamples, seed=a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    out_path = a.out / "report.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
