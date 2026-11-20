"""Course-lecture evaluation metrics for CashBooks Assist (offline).

Computes and writes tables to project/evaluation/results/final/:
  1. Reply-type classification (POS/NER lecture): accuracy vs majority-class baseline,
     4x5 confusion matrix (with UNPARSED column), per-class P/R/F1, and macro-F1.
  2. Retrieval at rank for C1/C2 (QA lecture): document-level P@k, R@k (k=1,3,5,8), MRR.
  3. Extraction NER-style P/R/F1 (via evaluation/extraction_metrics.py).
  4. Citation F1: mean per-turn F1 and micro-F1 alongside existing citation P/R.
  5. Paired McNemar significance (via evaluation/stats.py) & Attention C3/C4 summary
     compiled into project/evaluation/results/final/lecture_metrics_summary.md.

Held-out and development splits are always reported separately and never pooled.

    cd project
    python evaluation/lecture_metrics.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.evaluation import LogRow, QuerySuite
from cashbooks.scoring import _extract_reply_stats, doc_level, read_log, summarize

EVAL_DIR = Path(__file__).resolve().parent
PROJECT = EVAL_DIR.parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from attention_eval import evaluate_bundles as eval_attention  # noqa: E402
from extraction_metrics import evaluate_bundle as eval_ext_bundle, evaluate_sroie_jsonl, pool_bundle_results  # noqa: E402
from retrieval_diagnosis import analyze_run as analyze_retrieval, compute_retrieval_at_rank  # noqa: E402
from stats import pairwise_stats  # noqa: E402


def resolve_run_dir(run_dir: Path) -> Path:
    if run_dir.name != "rescored" and (run_dir / "rescored" / "log.jsonl").exists():
        return run_dir / "rescored"
    return run_dir

CLASSES = ("ANSWER", "CLARIFY", "ABSTAIN", "WARN")
PRED_COLS = ("ANSWER", "CLARIFY", "ABSTAIN", "WARN", "UNPARSED")

DEFAULT_HELDOUT_RUNS = [
    PROJECT / "evaluation" / "results" / "20261119-010517-landscaping_01-claude-haiku-5-5",
]
DEFAULT_DEV_RUNS = [
    PROJECT / "evaluation" / "results" / "20261118-223250-cafe_01-claude-haiku-5-5",
    PROJECT / "evaluation" / "results" / "20261118-224539-plumbing_01-claude-haiku-5-5",
]
DEFAULT_EXPANDED_DEV_RUNS = [
    PROJECT / "evaluation" / "results" / "20261118-231330-bakery_01-claude-haiku-5-5",
    PROJECT / "evaluation" / "results" / "20261118-232652-clinic_01-claude-haiku-5-5",
]
DEFAULT_OUT = PROJECT / "evaluation" / "results" / "final"


def _scored_rows(run_dirs: list[Path]) -> list[LogRow]:
    rows: list[LogRow] = []
    for d in run_dirs:
        rd = resolve_run_dir(d)
        rows.extend(
            r for r in read_log(rd / "log.jsonl")
            if not r.scores.get("setup_turn") and r.success is not None
        )
    return rows


def predicted_reply_type(row: LogRow) -> str:
    if not row.parsed_ok:
        return "UNPARSED"
    stats = _extract_reply_stats(row.raw_response)
    if stats is None or stats[2] not in CLASSES:
        return "UNPARSED"
    return str(stats[2])


def classification_metrics_from_matrix(
    cm: dict[str, dict[str, int]],
    classes: tuple[str, ...] = CLASSES,
    pred_cols: tuple[str, ...] = PRED_COLS,
) -> dict[str, Any]:
    """Compute accuracy, per-class P/R/F1, and macro-F1 from a confusion matrix."""
    total = sum(cm.get(e, {}).get(p, 0) for e in classes for p in pred_cols)
    correct = sum(cm.get(c, {}).get(c, 0) for c in classes)
    accuracy = (correct / total) if total > 0 else None

    per_class: dict[str, dict[str, Any]] = {}
    active_f1s: list[float] = []
    for c in classes:
        tp = cm.get(c, {}).get(c, 0)
        support = sum(cm.get(c, {}).get(p, 0) for p in pred_cols)
        pred_n = sum(cm.get(e, {}).get(c, 0) for e in classes)
        if support == 0 and pred_n == 0:
            per_class[c] = {"support": 0, "predicted": 0, "tp": 0, "precision": None, "recall": None, "f1": None}
            continue
        p = tp / pred_n if pred_n > 0 else 0.0
        r = tp / support if support > 0 else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        per_class[c] = {
            "support": support,
            "predicted": pred_n,
            "tp": tp,
            "precision": p,
            "recall": r,
            "f1": f1,
        }
        active_f1s.append(f1)

    macro_f1 = (sum(active_f1s) / len(active_f1s)) if active_f1s else None
    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "per_class": per_class,
        "macro_f1": macro_f1,
        "confusion_matrix": cm,
        "unparsed": sum(cm.get(e, {}).get("UNPARSED", 0) for e in classes),
    }


def evaluate_reply_classification(rows: list[LogRow]) -> dict[str, Any]:
    """Reply-type classification metrics and majority baseline per configuration."""
    configs = list(dict.fromkeys(r.configuration for r in rows))
    by_cfg: dict[str, Any] = {}
    majority_info: dict[str, Any] | None = None

    for cname in configs:
        crows = [r for r in rows if r.configuration == cname]
        exp_counts = Counter(r.expected.value for r in crows)
        total = len(crows)
        if exp_counts:
            maj_cls, maj_n = max(exp_counts.items(), key=lambda kv: (kv[1], kv[0]))
            maj_rate = maj_n / total
        else:
            maj_cls, maj_n, maj_rate = "n/a", 0, None

        if majority_info is None:
            majority_info = {"class": maj_cls, "count": maj_n, "total": total, "accuracy": maj_rate, "counts": dict(exp_counts)}

        cm = {e: {p: 0 for p in PRED_COLS} for e in CLASSES}
        for r in crows:
            exp = r.expected.value
            pred = predicted_reply_type(r)
            if exp in cm and pred in cm[exp]:
                cm[exp][pred] += 1

        metrics = classification_metrics_from_matrix(cm)
        metrics["majority_class"] = maj_cls
        metrics["majority_accuracy"] = maj_rate
        metrics["delta_vs_majority"] = (
            (metrics["accuracy"] - maj_rate)
            if (metrics["accuracy"] is not None and maj_rate is not None)
            else None
        )
        by_cfg[cname] = metrics

    return {"majority_baseline": majority_info, "configs": by_cfg}


def _load_gold_evidence_counts(run_dirs: list[Path]) -> dict[tuple[str, str, int], int]:
    """Return {(scenario, query_id, turn_index): len(gold_evidence)} across run folders."""
    counts: dict[tuple[str, str, int], int] = {}
    for d in run_dirs:
        rd = resolve_run_dir(d)
        bundle: Path | None = None
        for cand in (rd / "summary.json", d / "summary.json"):
            if cand.exists():
                b = json.loads(cand.read_text(encoding="utf-8")).get("bundle")
                if b:
                    bp = Path(b)
                    bundle = bp if bp.is_absolute() else (PROJECT / bp)
                    break
        if bundle is None:
            rows = read_log(rd / "log.jsonl")
            scen = rows[0].scenario if rows else ""
            cand_b = PROJECT / "data" / "dev" / scen
            bundle = cand_b if cand_b.exists() else (PROJECT / "data" / "test" / scen)
        if not (bundle / "gold.yaml").exists():
            continue
        qpath = (bundle / "queries.yaml") if (bundle / "queries.yaml").exists() else (PROJECT / "evaluation" / "queries.yaml")
        suite = QuerySuite.model_validate(yaml.safe_load(qpath.read_text(encoding="utf-8")))
        gold = yaml.safe_load((bundle / "gold.yaml").read_text(encoding="utf-8"))
        scen = bundle.name
        for conv in suite.conversations:
            g_entry = gold.get(conv.id, [])
            g_list = g_entry["turns"] if isinstance(g_entry, dict) else g_entry
            gi = 0
            for ti, t in enumerate(conv.turns):
                if not t.scored:
                    continue
                if gi < len(g_list):
                    counts[(scen, conv.id, ti)] = len(g_list[gi].get("evidence") or [])
                gi += 1
    return counts


def _raw_cited_count(raw_response: str) -> int:
    if not raw_response:
        return 0
    try:
        from cashbooks.scoring import _FENCE

        raw = raw_response.strip()
        m = _FENCE.fullmatch(raw)
        if m:
            raw = m.group(1)
        data = json.loads(raw)
        ev = data.get("evidence")
        if isinstance(ev, list):
            return len({doc_level(str(c["evidence_id"])) for c in ev if isinstance(c, dict) and c.get("evidence_id")})
    except Exception:
        pass
    return 0


def compute_citation_f1(
    rows: list[LogRow],
    gold_counts: dict[tuple[str, str, int], int] | None = None,
) -> dict[str, dict[str, Any]]:
    """Compute mean per-turn citation F1 and micro citation F1 per configuration."""
    configs = list(dict.fromkeys(r.configuration for r in rows))
    out: dict[str, dict[str, Any]] = {}
    for cname in configs:
        crows = [r for r in rows if r.configuration == cname]
        turn_f1s: list[float] = []
        tot_tp = 0.0
        tot_pred = 0.0
        tot_gold = 0.0
        for r in crows:
            er = r.scores.get("evidence_recall")
            ep = r.scores.get("evidence_precision")
            if er is None or ep is None:
                continue
            p = float(ep)
            rec = float(er)
            f1 = (2 * p * rec / (p + rec)) if (p + rec) > 0 else 0.0
            turn_f1s.append(f1)

            g_n = gold_counts.get((r.scenario, r.query_id, r.turn_index)) if gold_counts else None
            if g_n is not None and g_n > 0:
                tp = round(rec * g_n)
                if tp > 0 and p > 0:
                    p_n = round(tp / p)
                elif p == 0.0:
                    p_n = _raw_cited_count(r.raw_response) if r.parsed_ok else 0
                else:
                    p_n = 0
                tot_tp += tp
                tot_pred += p_n
                tot_gold += g_n
            else:
                tot_tp += rec
                tot_gold += 1.0
                if rec > 0 and p > 0:
                    tot_pred += rec / p
                else:
                    tot_pred += float(_raw_cited_count(r.raw_response))

        mean_f1 = (sum(turn_f1s) / len(turn_f1s)) if turn_f1s else None
        micro_p = (tot_tp / tot_pred) if tot_pred > 0 else (0.0 if turn_f1s else None)
        micro_r = (tot_tp / tot_gold) if tot_gold > 0 else None
        if micro_p is not None and micro_r is not None:
            micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) > 0 else 0.0
        else:
            micro_f1 = None
        out[cname] = {
            "turns_with_gold_cites": len(turn_f1s),
            "mean_f1": mean_f1,
            "micro_precision": micro_p,
            "micro_recall": micro_r,
            "micro_f1": micro_f1,
        }
    return out


def evaluate_retrieval_split(run_dirs: list[Path]) -> dict[str, Any]:
    all_turns: list[dict[str, Any]] = []
    for d in run_dirs:
        analysis = analyze_retrieval(d)
        all_turns.extend(analysis["turns"])
    return compute_retrieval_at_rank(all_turns)


def _fmt_pct(v: float | None, decimals: int = 1) -> str:
    return "n/a" if v is None else f"{v * 100:.{decimals}f}%"


def _fmt_f(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def format_reply_classification_md(splits: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Reply-Type Classification (POS / NER Lecture)",
        "",
        "Compares predicted `answerability` across `{ANSWER, CLARIFY, ABSTAIN, WARN}` (plus `UNPARSED`) against a majority-class baseline that always predicts the most frequent expected label in that split.",
        "",
    ]
    for sname, data in splits.items():
        maj = data["majority_baseline"]
        maj_str = f"`{maj['class']}` ({maj['count']}/{maj['total']} = {maj['accuracy']:.1%})" if maj else "n/a"
        lines.extend([
            f"## {sname}",
            "",
            f"Majority-class baseline: {maj_str}.",
            "",
            "| Config | Turns | Accuracy | Majority baseline | vs Majority | Macro-F1 | ANSWER F1 | CLARIFY F1 | ABSTAIN F1 | WARN F1 | Unparsed |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for cname, m in data["configs"].items():
            pc = m["per_class"]
            delta_str = "n/a" if m["delta_vs_majority"] is None else f"{m['delta_vs_majority']:+.1%}"
            lines.append(
                f"| {cname} | {m['total']} | {_fmt_pct(m['accuracy'])} | {_fmt_pct(m['majority_accuracy'])} | "
                f"{delta_str} | {_fmt_f(m['macro_f1'])} | {_fmt_f(pc['ANSWER']['f1'])} | {_fmt_f(pc['CLARIFY']['f1'])} | "
                f"{_fmt_f(pc['ABSTAIN']['f1'])} | {_fmt_f(pc['WARN']['f1'])} | {m['unparsed']} |"
            )
        lines.append("")
        for cname, m in data["configs"].items():
            lines.extend([
                f"### {sname} — {cname} confusion matrix and per-class P/R/F1",
                "",
                "| Expected \\ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ])
            cm = m["confusion_matrix"]
            for exp in CLASSES:
                row_counts = [str(cm[exp][p]) for p in PRED_COLS]
                cs = m["per_class"][exp]
                lines.append(
                    f"| {exp} | " + " | ".join(row_counts)
                    + f" | {cs['support']} | {_fmt_f(cs['precision'])} | {_fmt_f(cs['recall'])} | {_fmt_f(cs['f1'])} |"
                )
            lines.append("")
    return "\n".join(lines)


def format_retrieval_split_md(splits: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Document-Level Retrieval at Rank for C1 and C2 (QA Lecture)",
        "",
        "Precision@k, Recall@k (k = 1, 3, 5, 8), and Mean Reciprocal Rank (MRR) of the first gold evidence document.",
        "",
    ]
    for sname, rank_stats in splits.items():
        lines.extend([
            f"## {sname}",
            "",
            "| Config | Turns w/ gold | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for cfg in ("C1", "C2"):
            st = rank_stats.get(cfg)
            if not st or not st["turns_with_gold"]:
                lines.append(f"| {cfg} | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
                continue
            p_cells = [f"{st['precision_at_k'][k]:.3f}" for k in (1, 3, 5, 8)]
            r_cells = [f"{st['recall_at_k'][k]:.3f}" for k in (1, 3, 5, 8)]
            lines.append(
                f"| {cfg} | {st['turns_with_gold']} | "
                + " | ".join(p_cells + r_cells)
                + f" | {st['mrr']:.3f} |"
            )
        lines.append("")
    return "\n".join(lines)


def format_citation_f1_md(splits: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Citation Precision, Recall, and F1",
        "",
        "Computed over scored turns with gold citations, reporting mean per-turn citation recall/precision/F1 and corpus micro-F1.",
        "",
    ]
    for sname, data in splits.items():
        lines.extend([
            f"## {sname}",
            "",
            "| Config | Turns w/ gold cites | Mean recall | Mean precision | Mean F1 | Micro-F1 (P / R) |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        sum_d = data["summary"]
        cf1_d = data["citation_f1"]
        for cname in sum_d:
            s = sum_d[cname]
            cf = cf1_d[cname]
            mr = _fmt_f(s["mean_evidence_recall"])
            mp = _fmt_f(s["mean_evidence_precision"])
            mf1 = _fmt_f(cf["mean_f1"])
            uf1 = f"{_fmt_f(cf['micro_f1'])} ({_fmt_f(cf['micro_precision'])} / {_fmt_f(cf['micro_recall'])})"
            lines.append(f"| {cname} | {cf['turns_with_gold_cites']} | {mr} | {mp} | {mf1} | {uf1} |")
        lines.append("")
    return "\n".join(lines)


def build_summary_md(
    cls_splits: dict[str, Any],
    ret_splits: dict[str, Any],
    ext_report: dict[str, Any],
    cit_splits: dict[str, Any],
    sig_splits: dict[str, Any],
    attn_report: dict[str, Any],
) -> str:
    """Build compact summary document with Held-out first and lecture concept labels."""
    lines = [
        "# Course-Lecture Evaluation Metrics Summary",
        "",
        "Offline evaluation on `answer_system_v2` (commit `7a5dd10`). Held-out (`landscaping_01`) and development splits are never pooled.",
        "",
        "---",
        "",
        "## 1. Reply-Type Classification (POS / NER lecture: accuracy vs most-frequent-class baseline)",
        "",
    ]
    for sname, data in cls_splits.items():
        maj = data["majority_baseline"]
        lines.extend([
            f"### {sname} (Majority baseline: `{maj['class']}` = {maj['count']}/{maj['total']} = {maj['accuracy']:.1%})",
            "",
            "| Config | Accuracy | vs Majority | Macro-F1 | ANSWER F1 | CLARIFY F1 | ABSTAIN F1 | WARN F1 | Unparsed |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for cname, m in data["configs"].items():
            pc = m["per_class"]
            delta_str = "n/a" if m["delta_vs_majority"] is None else f"{m['delta_vs_majority']:+.1%}"
            lines.append(
                f"| {cname} | {_fmt_pct(m['accuracy'])} | {delta_str} | {_fmt_f(m['macro_f1'])} | "
                f"{_fmt_f(pc['ANSWER']['f1'])} | {_fmt_f(pc['CLARIFY']['f1'])} | "
                f"{_fmt_f(pc['ABSTAIN']['f1'])} | {_fmt_f(pc['WARN']['f1'])} | {m['unparsed']} |"
            )
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 2. Document-Level Retrieval at Rank for C1 and C2 (QA lecture: precision at rank, recall by rank, MRR)",
        "",
        "| Split | Config | Turns w/ gold | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for sname, rank_stats in ret_splits.items():
        for cfg in ("C1", "C2"):
            st = rank_stats.get(cfg)
            if not st or not st["turns_with_gold"]:
                continue
            p_cells = [f"{st['precision_at_k'][k]:.3f}" for k in (1, 3, 5, 8)]
            r_cells = [f"{st['recall_at_k'][k]:.3f}" for k in (1, 3, 5, 8)]
            lines.append(
                f"| {sname} | {cfg} | {st['turns_with_gold']} | "
                + " | ".join(p_cells + r_cells)
                + f" | {st['mrr']:.3f} |"
            )
    lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. NER-Style Extraction Precision, Recall, and F1 (NER lecture: unit exact match, partial = 1 FP + 1 FN)",
        "",
        "| Split / Dataset | Docs | Overall Micro-P | Overall Micro-R | Overall Micro-F1 | Total F1 | Line-Items F1 | Subtotals/Tax note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for hname, hd in ext_report.get("held_out", {}).items():
        ov = hd["overall_micro"]
        tf1 = hd["fields"]["total"]["f1"]
        lf1 = hd["fields"]["line_items"]["f1"]
        sub_fn = hd["fields"]["subtotal"]["fn"] + hd["fields"]["tax"]["fn"]
        lines.append(
            f"| Held-out (`{hname}`) | {hd['documents']} | {_fmt_f(ov['precision'])} | {_fmt_f(ov['recall'])} | "
            f"{_fmt_f(ov['f1'])} | {_fmt_f(tf1)} | {_fmt_f(lf1)} | subtotal+tax FN={sub_fn} |"
        )
    if ext_report.get("dev_pooled"):
        dp = ext_report["dev_pooled"]
        ov = dp["overall_micro"]
        tf1 = dp["fields"]["total"]["f1"]
        lf1 = dp["fields"]["line_items"]["f1"]
        sub_fn = dp["fields"]["subtotal"]["fn"] + dp["fields"]["tax"]["fn"]
        lines.append(
            f"| Development (`cafe_01 + plumbing_01`) | {dp['documents']} | {_fmt_f(ov['precision'])} | {_fmt_f(ov['recall'])} | "
            f"{_fmt_f(ov['f1'])} | {_fmt_f(tf1)} | {_fmt_f(lf1)} | subtotal+tax FN={sub_fn} |"
        )
    if ext_report.get("sroie"):
        sr = ext_report["sroie"]
        ov = sr["overall_micro"]
        cf1 = sr["fields"]["company"]["f1"]
        df1 = sr["fields"]["date"]["f1"]
        tf1 = sr["fields"]["total"]["f1"]
        lines.append(
            f"| Real receipts (`SROIE`: company/date/total) | {sr['documents']} | {_fmt_f(ov['precision'])} | {_fmt_f(ov['recall'])} | "
            f"{_fmt_f(ov['f1'])} | {_fmt_f(tf1)} | — | company={_fmt_f(cf1)}, date={_fmt_f(df1)} |"
        )
    lines.append("")

    lines.extend([
        "---",
        "",
        "## 4. Citation F1 (mean per-turn F1 and corpus micro-F1)",
        "",
        "| Split | Config | Mean recall | Mean precision | Mean F1 | Micro-F1 |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for sname, data in cit_splits.items():
        sum_d = data["summary"]
        cf1_d = data["citation_f1"]
        for cname in sum_d:
            s = sum_d[cname]
            cf = cf1_d[cname]
            lines.append(
                f"| {sname} | {cname} | {_fmt_f(s['mean_evidence_recall'])} | "
                f"{_fmt_f(s['mean_evidence_precision'])} | {_fmt_f(cf['mean_f1'])} | {_fmt_f(cf['micro_f1'])} |"
            )
    lines.append("")

    lines.extend([
        "---",
        "",
        "## 5. Significance Testing & Attention-Item Evaluation (NER lecture: paired exact McNemar & `(scenario, query_id)` bootstrap)",
        "",
        "| Split | Pair (A vs B) | Discordant (A:B) | Exact McNemar p | Diff (A - B) | 95% Bootstrap CI |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for sname, pairs in sig_splits.items():
        for r in pairs:
            lines.append(
                f"| {sname} | {r['a']} vs {r['b']} | {r['b_only']}:{r['c_only']} | {r['p_value']:.3f} | "
                f"{r['diff']:+.1%} | [{r['ci_low']:+.1%}, {r['ci_high']:+.1%}] |"
            )
    lines.extend([
        "",
        "### Attention-item detection (C3 extracted vs C4 gold)",
        "",
        "| Split | Bundle | Store | Expected | Found | TP | Precision | Recall |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for s_label, skey in (("Held-out", "held_out"), ("Development", "dev")):
        for bname, stores in attn_report.get(skey, {}).items():
            for st_name in ("C3", "C4"):
                sc = stores.get(st_name)
                if not sc:
                    continue
                lines.append(
                    f"| {s_label} | {bname} | {st_name} | {sc['expected']} | {sc['found']} | {sc['tp']} | "
                    f"{_fmt_pct(sc['precision'])} | {_fmt_pct(sc['recall'])} |"
                )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--held-out-runs", nargs="+", type=Path, default=DEFAULT_HELDOUT_RUNS)
    ap.add_argument("--dev-runs", nargs="+", type=Path, default=DEFAULT_DEV_RUNS)
    ap.add_argument("--expanded-dev-runs", nargs="+", type=Path, default=DEFAULT_EXPANDED_DEV_RUNS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)

    split_specs = [
        ("Held-out (landscaping_01)", a.held_out_runs),
        ("Development (cafe_01 + plumbing_01)", a.dev_runs),
        ("Expanded development (bakery_01 + clinic_01)", a.expanded_dev_runs),
    ]

    cls_splits: dict[str, Any] = {}
    ret_splits: dict[str, Any] = {}
    cit_splits: dict[str, Any] = {}
    sig_splits: dict[str, Any] = {}

    for label, run_dirs in split_specs:
        rows = _scored_rows(run_dirs)
        gold_counts = _load_gold_evidence_counts(run_dirs)
        cls_splits[label] = evaluate_reply_classification(rows)
        ret_splits[label] = evaluate_retrieval_split(run_dirs)
        cit_splits[label] = {
            "summary": summarize(rows),
            "citation_f1": compute_citation_f1(rows, gold_counts),
        }
        resolved = [resolve_run_dir(d) for d in run_dirs]
        _, pairs, _ = pairwise_stats(resolved)
        sig_splits[label] = pairs

    ext_held = {b.name: eval_ext_bundle(b) for b in [PROJECT / "data" / "test" / "landscaping_01"]}
    ext_dev_list = [eval_ext_bundle(b) for b in [PROJECT / "data" / "dev" / "cafe_01", PROJECT / "data" / "dev" / "plumbing_01"]]
    sroie_path = PROJECT / "data" / "real" / "runs" / "20261117-163026-sroie-claude-haiku-5-5.jsonl"
    ext_report = {
        "held_out": ext_held,
        "dev": {d["bundle"]: d for d in ext_dev_list},
        "dev_pooled": pool_bundle_results(ext_dev_list),
        "sroie": evaluate_sroie_jsonl(sroie_path) if sroie_path.exists() else None,
    }
    attn_report = eval_attention()

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "reply_classification.md").write_text(format_reply_classification_md(cls_splits), encoding="utf-8")
    (a.out / "reply_classification.json").write_text(json.dumps(cls_splits, indent=2) + "\n", encoding="utf-8")
    (a.out / "retrieval_at_rank.md").write_text(format_retrieval_split_md(ret_splits), encoding="utf-8")
    (a.out / "retrieval_at_rank.json").write_text(json.dumps(ret_splits, indent=2) + "\n", encoding="utf-8")
    (a.out / "citation_f1.md").write_text(format_citation_f1_md(cit_splits), encoding="utf-8")
    (a.out / "citation_f1.json").write_text(json.dumps(cit_splits, indent=2) + "\n", encoding="utf-8")

    summary_md = build_summary_md(cls_splits, ret_splits, ext_report, cit_splits, sig_splits, attn_report)
    (a.out / "lecture_metrics_summary.md").write_text(summary_md, encoding="utf-8")
    print(f"wrote lecture metrics tables and summary to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
