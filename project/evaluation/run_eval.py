"""Run configurations over the frozen conversations for one scenario, score every
turn, and write the logs and summaries.

    cd project
    python evaluation/run_eval.py data/dev/cafe_01 --configs C1 C4            # default model (key in code/.env)
    python evaluation/run_eval.py data/dev/cafe_01 --configs C1 C2 C3 C4 --queries Q01 Q04
    python evaluation/run_eval.py data/dev/cafe_01 --llm scripted             # offline dry run

C2 and C3 read extracted records, so run evaluation/extract_bundle.py first.

Writes evaluation/results/<run id>/:
    log.jsonl     one row per (configuration, conversation, turn): context, raw reply, scores
    course.csv    query, expected behavior, response, success, notes (the course's five fields)
    summary.json  per-configuration metrics
    summary.md    the same as tables, plus conversation-level success
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from cashbooks.configs.answer import PROMPT_VERSION, Turn, build_configs, format_turn_assistant
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow, QuerySuite
from cashbooks.contracts.postprocess import postprocess
from cashbooks.eval_specs import (
    DEFAULT_POLICY,
    EvaluationSpecError,
    apply_turn_overrides,
    build_run_metadata,
    load_eval_spec,
)
from cashbooks.scoring import SCORER_VERSION, score_turn, write_log, write_run_outputs
from cashbooks.store.db import Store
from cashbooks.store.load_gold import load_gold

PROJECT = Path(__file__).resolve().parents[1]


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT, text=True).strip()
    except Exception:
        return "unknown"


def make_llm(kind: str, model: str | None):
    if kind == "scripted":
        from cashbooks.llm.scripted import ScriptedLLM
        return ScriptedLLM()
    if kind == "claude":
        from cashbooks.llm.claude import ClaudeLLM
        return ClaudeLLM(model=model)
    from cashbooks.llm.gemini import GeminiLLM
    return GeminiLLM(model=model)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--configs", nargs="+", default=["C1", "C2", "C3", "C4"])
    ap.add_argument("--queries", nargs="*", help="conversation IDs to run (default: all with gold)")
    ap.add_argument("--llm", choices=["claude", "gemini", "scripted"], default="claude")
    ap.add_argument("--model", help="override LLM_MODEL")
    ap.add_argument("--queries-file", type=Path, help="query manifest YAML (default evaluation/queries.yaml)")
    ap.add_argument(
        "--eval-spec",
        type=Path,
        default=None,
        help="optional versioned evaluation spec YAML (e.g. evaluation/specs_v3_1/amount_semantics_overrides.yaml); omit for legacy strict_historical policy",
    )
    ap.add_argument("--out", type=Path, help="results folder (default evaluation/results/<timestamp>)")
    a = ap.parse_args(argv)

    qpath = a.queries_file or (PROJECT / "evaluation" / "queries.yaml")
    gold_path = a.bundle / "gold.yaml"
    suite = QuerySuite.model_validate(yaml.safe_load(qpath.read_text(encoding="utf-8")))
    gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))
    eval_spec = None
    if a.eval_spec is not None:
        try:
            eval_spec = load_eval_spec(a.eval_spec, a.bundle.name, suite, gold)
        except EvaluationSpecError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    ledger = json.loads((a.bundle / "ledger.json").read_text(encoding="utf-8"))
    biz = ledger["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])
    convs = [c for c in suite.conversations if c.id in gold and (not a.queries or c.id in a.queries)]
    if not convs:
        print("no conversations to run")
        return 1

    gold_store, _ = load_gold(a.bundle)
    extracted = None
    xdb = a.bundle / "extracted.sqlite"
    if xdb.exists():
        conn = sqlite3.connect(str(xdb))
        conn.row_factory = sqlite3.Row
        extracted = Store(conn, biz["business_id"])
    configs = build_configs(a.bundle, gold_store, extracted, biz["name"], as_of, a.configs)
    llm = make_llm(a.llm, a.model)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{a.bundle.name}-{llm.model}"
    out = a.out or PROJECT / "evaluation" / "results" / run_id
    out.mkdir(parents=True, exist_ok=True)
    commit = git_commit()
    rows: list[LogRow] = []

    for cname, cfg in configs.items():
        for conv in convs:
            history: list[Turn] = []
            gold_entry = gold[conv.id]
            gold_turns = list(gold_entry.get("turns", []) if isinstance(gold_entry, dict) else gold_entry)
            setup_text = gold_entry.get("setup_text") if isinstance(gold_entry, dict) else None
            gi = 0
            for ti, turn in enumerate(conv.turns):
                g = (gold_turns[gi] if gi < len(gold_turns) else {}) if turn.scored else {}
                if turn.scored:
                    gi += 1
                    t_text = str(g.get("text") or turn.text)
                else:
                    t_text = str(setup_text or turn.text)
                o = cfg.answer(llm, history, t_text)
                raw = o.result.text
                pp = postprocess(raw, o.known_evidence, default_as_of=as_of) if raw else None
                resp = pp.response if pp else None
                notes = []
                if o.result.error:
                    notes.append(f"llm_error: {o.result.error[:300]}")
                if pp:
                    notes += pp.issues + [f"wording: {w}" for w in pp.wording_flags]
                if turn.scored:
                    eff_values = apply_turn_overrides(g.get("values", {}), eval_spec, conv.id, ti)
                    sc = score_turn(resp, turn.expected, eff_values, g.get("evidence", []),
                                    list(turn.must_not) + list(g.get("must_not", [])))
                    scores, success = sc.to_dict(), sc.success
                else:
                    scores, success = {"setup_turn": True}, None
                    notes.append("setup turn, not scored")
                row = LogRow(
                    query_id=conv.id, turn_index=ti, turn_text=t_text, scenario=a.bundle.name,
                    business_type=biz.get("type", ""), split="dev", configuration=cname,
                    model_version=llm.model, prompt_version=PROMPT_VERSION, code_commit=commit,
                    context=o.context, raw_response=raw, parsed_ok=resp is not None, expected=turn.expected,
                    success=success, scores=scores, notes="; ".join(notes),
                    latency_ms=o.result.latency_ms, input_tokens=o.result.input_tokens, output_tokens=o.result.output_tokens,
                )
                write_log([row], out / "log.jsonl")
                if turn.scored:
                    rows.append(row)
                mark = "-" if success is None else ("ok" if success else "FAIL")
                print(f"{cname} {conv.id} t{ti} {mark:4} {resp.answerability.value if resp else 'unparsed':8} "
                      f"{(resp.answer if resp else raw)[:90]!r}")
                history.append(Turn(t_text, format_turn_assistant(resp, raw)))

    qlabels = {c.id: list(c.labels) for c in suite.conversations}
    lines = write_run_outputs(rows, out, run_id, llm.model, commit, str(a.bundle), [c.id for c in convs],
                              sum(1 for c in convs for t in c.turns if t.scored), PROMPT_VERSION,
                              query_labels=qlabels)
    metadata = build_run_metadata(
        project_root=PROJECT,
        run_id=run_id,
        bundle=a.bundle,
        queries_path=qpath,
        gold_path=gold_path,
        model_version=llm.model,
        prompt_version=PROMPT_VERSION,
        loaded_spec=eval_spec,
        rows=rows,
    )
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    # Append policy provenance and predeclared invariant-subset reporting (e.g. Q13 on scaled cafe bundles) to summary.md
    extra_md = [
        "",
        "## Scoring Policy & Provenance",
        "",
        f"- Scorer version: `{SCORER_VERSION}`",
        f"- Selected scoring policy: `{metadata['scoring_policy']}`"
        + (f" (`{eval_spec.spec_path.name}`, scenario `{eval_spec.resolved_scenario}`)" if eval_spec else " (legacy default)"),
        f"- Metadata & hashes: `metadata.json`",
    ]
    if "invariant_subset_summary" in metadata:
        inv = metadata["invariant_subset_summary"]
        excl = ", ".join(inv["excluded_corpus_sensitive_queries"])
        extra_md += [
            "",
            f"## Predeclared Invariant-Task Subset vs. Corpus-Sensitive Queries (`{excl}`)",
            "",
        ]
        for qid, qinfo in metadata.get("corpus_sensitive_queries", {}).items():
            extra_md.append(f"- `{qid}`: {qinfo['reason']}")
        extra_md += [
            "",
            f"| Config | All Turns | Invariant Subset (excl. {excl}) | Corpus-Sensitive ({excl}) |",
            "| --- | --- | --- | --- |",
        ]
        for cname, st in inv["per_config"].items():
            a_st = st["all_turns"]
            i_st = st["invariant_subset"]
            c_st = st["corpus_sensitive_subset"]
            c_str = f"{c_st['successes']}/{c_st['turns']} ({c_st['rate']:.0%})" if c_st["turns"] else "0/0"
            extra_md.append(
                f"| {cname} | {a_st['successes']}/{a_st['turns']} ({a_st['rate']:.0%}) | "
                f"{i_st['successes']}/{i_st['turns']} ({i_st['rate']:.0%}) | {c_str} |"
            )
    summary_md_path = out / "summary.md"
    summary_md_path.write_text(summary_md_path.read_text(encoding="utf-8") + "\n".join(extra_md) + "\n", encoding="utf-8")

    print(f"\nwrote {out} (policy={metadata['scoring_policy']})")
    print("\n".join(lines[4:4 + len(configs) + 2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
