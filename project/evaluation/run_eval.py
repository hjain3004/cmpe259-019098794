"""Run configurations over the frozen conversations for one scenario, score every
turn, and write the logs and summaries.

    cd project
    python evaluation/run_eval.py data/dev/cafe_01 --configs C1 C4            # Gemini (key in code/.env)
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

from cashbooks.configs.answer import PROMPT_VERSION, Turn, build_configs
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import LogRow, QuerySuite
from cashbooks.contracts.postprocess import postprocess
from cashbooks.scoring import conversation_success, dump_json, export_course_csv, score_turn, summarize, write_log
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
    from cashbooks.llm.gemini import GeminiLLM
    return GeminiLLM(model=model)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--configs", nargs="+", default=["C1", "C2", "C3", "C4"])
    ap.add_argument("--queries", nargs="*", help="conversation IDs to run (default: all with gold)")
    ap.add_argument("--llm", choices=["gemini", "scripted"], default="gemini")
    ap.add_argument("--model", help="override LLM_MODEL")
    ap.add_argument("--out", type=Path, help="results folder (default evaluation/results/<timestamp>)")
    a = ap.parse_args()

    suite = QuerySuite.model_validate(yaml.safe_load((PROJECT / "evaluation" / "queries.yaml").read_text()))
    gold = yaml.safe_load((a.bundle / "gold.yaml").read_text())
    ledger = json.loads((a.bundle / "ledger.json").read_text())
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
            gold_turns = list(gold[conv.id])
            gi = 0
            for ti, turn in enumerate(conv.turns):
                o = cfg.answer(llm, history, turn.text)
                raw = o.result.text
                pp = postprocess(raw, o.known_evidence) if raw else None
                resp = pp.response if pp else None
                notes = []
                if o.result.error:
                    notes.append(f"llm_error: {o.result.error[:300]}")
                if pp:
                    notes += pp.issues + [f"wording: {w}" for w in pp.wording_flags]
                if turn.scored:
                    g = gold_turns[gi] if gi < len(gold_turns) else {}
                    gi += 1
                    sc = score_turn(resp, turn.expected, g.get("values", {}), g.get("evidence", []),
                                    list(turn.must_not) + list(g.get("must_not", [])))
                    scores, success = sc.to_dict(), sc.success
                else:
                    scores, success = {"setup_turn": True}, None
                    notes.append("setup turn, not scored")
                row = LogRow(
                    query_id=conv.id, turn_index=ti, turn_text=turn.text, scenario=a.bundle.name,
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
                history.append(Turn(turn.text, resp.answer if resp else raw[:800]))

    export_course_csv(rows, out / "course.csv")
    summary = summarize(rows)
    conv = conversation_success(rows)
    for cname, per in conv.items():
        summary[cname]["conversations"] = len(per)
        summary[cname]["conversation_successes"] = sum(per.values())
    dump_json({"run": run_id, "model": llm.model, "commit": commit, "bundle": str(a.bundle),
               "configs": summary, "per_conversation": conv}, out / "summary.json")

    lines = [f"# Run {run_id}", "", f"Model `{llm.model}`, prompt `{PROMPT_VERSION}`, commit `{commit}`, "
             f"scenario `{a.bundle.name}`, {len(convs)} conversations, {sum(1 for c in convs for t in c.turns if t.scored)} scored turns.", "",
             "| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for cname, s in summary.items():
        lines.append(f"| {cname} | {s['successes']}/{s['turns']} ({s['success_rate']:.0%}) | "
                     f"{s['conversation_successes']}/{s['conversations']} | {s['answer_type_accuracy']:.0%} | "
                     f"{s['value_accuracy'] if s['value_accuracy'] is None else format(s['value_accuracy'], '.0%')} | "
                     f"{s['parsed']}/{s['turns']} | {s['median_latency_s']} | {s['mean_tokens']} |")
    ids = [c.id for c in convs]
    lines += ["", "## Conversation success", "", "| Conversation | " + " | ".join(conv) + " |",
              "| --- |" + " --- |" * len(conv)]
    for q in ids:
        lines.append(f"| {q} | " + " | ".join("pass" if conv[c].get(q) else "fail" for c in conv) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out}")
    print("\n".join(lines[4:4 + len(summary) + 2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
