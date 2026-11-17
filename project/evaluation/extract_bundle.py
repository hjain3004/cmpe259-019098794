"""Extract one scenario's documents into the records C2 and C3 read, and score the
extraction against the ledger.

    cd project
    python evaluation/extract_bundle.py data/dev/cafe_01                 # Gemini (key in code/.env)
    python evaluation/extract_bundle.py data/dev/cafe_01 --llm reference # offline check of the pipeline

Writes:
    <bundle>/extracted.sqlite                         (gitignored; rebuilt on every run)
    evaluation/results/<run id>/extraction_calls.jsonl  every model call: raw output, parse result, notes
    evaluation/results/<run id>/extraction_report.json  field accuracy against the ledger, and every error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from cashbooks.extract.pipeline import extract_bundle, score_extraction
from cashbooks.store.db import connect

PROJECT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--llm", choices=["gemini", "reference"], default="gemini")
    ap.add_argument("--model", help="override LLM_MODEL")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    if a.llm == "reference":
        from cashbooks.extract.reference import ReferenceExtractor
        llm = ReferenceExtractor(a.bundle)
    else:
        from cashbooks.llm.gemini import GeminiLLM
        llm = GeminiLLM(model=a.model)

    db = a.bundle / "extracted.sqlite"
    if db.exists():
        db.unlink()
    run = extract_bundle(a.bundle, llm, db)
    run.store.conn.commit()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-extract-{a.bundle.name}-{llm.model}"
    out = a.out or PROJECT / "evaluation" / "results" / run_id
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "extraction_calls.jsonl", "w") as f:
        for c in run.calls:
            f.write(json.dumps(asdict(c)) + "\n")
    report = score_extraction(a.bundle, run.extracted)
    failed = [c for c in run.calls if not c.ok]
    report.update({
        "model": llm.model, "bundle": str(a.bundle), "calls": len(run.calls), "failed_calls": len(failed),
        "input_tokens": sum(c.input_tokens for c in run.calls), "output_tokens": sum(c.output_tokens for c in run.calls),
        "ungrounded": {k: v["ungrounded"] for k, v in run.extracted["invoices"].items() if v["ungrounded"]},
    })
    (out / "extraction_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")

    n = {t: run.store.conn.execute(f"select count(*) from {t}").fetchone()[0]
         for t in ("bills", "bill_lines", "credits", "message_claims", "payment_links")}
    print(f"wrote {db}: " + ", ".join(f"{k}={v}" for k, v in n.items()))
    print(f"calls {len(run.calls)}, failed {len(failed)}; field accuracy {report['correct']}/{report['fields']} "
          f"({report['accuracy']:.0%})")
    for e in report["errors"][:15]:
        print(f"  {e['doc']} {e['field']}: gold {e['gold']!r}, extracted {e['extracted']!r}")
    for c in failed:
        print(f"  failed call {c.doc} {c.schema}: {c.error}")
    print(f"report in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
