"""Re-score a finished run from its saved replies, without calling any model.

Use after a fix to parsing or scoring (never to the prompts or the model): the
saved raw replies are run through the current post-processing and scorer, and
the results go to <run>/rescored/, next to the original files, which are kept.

    cd project
    python evaluation/rescore.py evaluation/results/<run id> data/dev/cafe_01
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import yaml

from cashbooks.configs.answer import PROMPT_VERSION, build_configs
from cashbooks.contracts.evaluation import LogRow, QuerySuite
from cashbooks.contracts.postprocess import postprocess
from cashbooks.scoring import _is_identifier, read_log, score_turn, write_log, write_run_outputs
from cashbooks.store.db import Store
from cashbooks.store.load_gold import load_gold

PROJECT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--queries-file", type=Path, help="query manifest YAML (default evaluation/queries.yaml)")
    a = ap.parse_args()

    qpath = a.queries_file or (PROJECT / "evaluation" / "queries.yaml")
    suite = QuerySuite.model_validate(yaml.safe_load(qpath.read_text()))
    specs = {c.id: c for c in suite.conversations}
    gold = yaml.safe_load((a.bundle / "gold.yaml").read_text())
    ledger = json.loads((a.bundle / "ledger.json").read_text())
    biz = ledger["business"]
    gold_store, _ = load_gold(a.bundle)
    conn = sqlite3.connect(str(a.bundle / "extracted.sqlite"))
    conn.row_factory = sqlite3.Row
    rows = read_log(a.run / "log.jsonl")
    names = sorted({r.configuration for r in rows})
    as_of = date.fromisoformat(biz["evaluation_clock"])
    known = {n: c.known for n, c in build_configs(a.bundle, gold_store, Store(conn, biz["business_id"]), biz["name"],
                                                  as_of, names).items()}

    out = a.run / "rescored"
    out.mkdir(exist_ok=True)
    (out / "log.jsonl").unlink(missing_ok=True)
    scored: list[LogRow] = []
    changed = 0
    for r in rows:
        spec = specs[r.query_id]
        turn = spec.turns[r.turn_index]
        if not turn.scored:
            write_log([r], out / "log.jsonl")
            continue
        gi = sum(1 for t in spec.turns[: r.turn_index] if t.scored)
        gold_entry = gold[r.query_id]
        gold_turns = list(gold_entry.get("turns", []) if isinstance(gold_entry, dict) else gold_entry)
        g = gold_turns[gi] if gi < len(gold_turns) else {}
        pp = postprocess(r.raw_response, known[r.configuration], default_as_of=as_of) if r.raw_response else None
        resp = pp.response if pp else None
        sc = score_turn(resp, turn.expected, g.get("values", {}), g.get("evidence", []),
                        list(turn.must_not) + list(g.get("must_not", [])))
        notes = [n for n in r.notes.split("; ") if n.startswith("llm_error")] + (pp.issues if pp else []) + \
                ([f"wording: {w}" for w in pp.wording_flags] if pp else []) + \
                [f"must_not_identifier: {p}" for p in sc.must_not_hits if _is_identifier(p)] + \
                [f"skipped_must_not: {p}" for p in sc.must_not_skipped]
        new = r.model_copy(update={"parsed_ok": resp is not None, "success": sc.success, "scores": sc.to_dict(),
                                   "notes": "; ".join(notes)})
        changed += int(new.success != r.success)
        write_log([new], out / "log.jsonl")
        scored.append(new)

    meta = json.loads((a.run / "summary.json").read_text())
    conv_ids = [q for q in gold if q in specs and q in {r.query_id for r in rows}]
    qlabels = {c.id: list(c.labels) for c in suite.conversations}
    lines = write_run_outputs(scored, out, meta["run"] + " (rescored)", meta["model"], meta["commit"], str(a.bundle),
                              conv_ids, len(scored) // len(names), meta.get("prompt_version", PROMPT_VERSION),
                              query_labels=qlabels)
    print(f"{changed} turn verdicts changed; wrote {out}")
    print("\n".join(lines[4:4 + len(names) + 2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
