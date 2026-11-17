# CashBooks Assist

A read-only LLM assistant that answers questions about vendor bills and payments for owner-operated
small businesses (1–20 employees, no accounts-payable staff), and a harness that compares four
configurations of it on the same documents, model and questions:

| Config | What the answering model receives |
|---|---|
| C1 | BM25-retrieved chunks of raw invoices, messages and bank rows |
| C2 | Retrieved typed records (same retriever and k as C1) |
| C3 | Results of seven read-only deterministic tools over the extracted records |
| C4 | C3 on hand-verified gold records (isolates extraction error) |

## Documents

- [`proposal/proposal.pdf`](proposal/proposal.pdf): the submitted proposal (11 Sep 2026), unchanged
- [`docs/design.md`](docs/design.md): design and implementation plan
- [`docs/decisions.md`](docs/decisions.md): every change from the proposal or plan, with reasons
- [`docs/references.md`](docs/references.md): reading list and what each paper is used for; BibTeX in [`docs/references.bib`](docs/references.bib)
- [`checkins/`](checkins/): check-in reports

## Status

Phase 1 is done and C1 to C4 run end to end on the café development scenario. The extraction
pipeline, all seven tools, both retrievers, the run harness and the scorer are implemented and
tested offline. Runs against Gemini are next.

```
code/src/cashbooks/
  contracts/   typed interfaces between every stage (extraction, records, tools, response, eval)
  ingest/      PDF page text, bank CSV parser, bundle readers
  normalize/   money, dates, payment terms, vendor names, account fingerprints
  store/       SQLite schema, Store (scoped to one business), gold loader
  tools/       the seven read-only tools, payment matching, tool dispatch
  extract/     model extraction into records; a reference extractor for offline checks
  configs/     BM25 retrieval (C1, C2) and the four answering configurations
  llm/         model interface, Gemini client, scripted stand-in for tests
  scoring.py   deterministic scoring, run logs, course CSV
prompts/       answering and extraction prompts (versioned by file name)
data/generator/render.py   renders a ledger into invoice PDFs, messages, bank CSV, vendor record
data/dev/cafe_01/          café scenario: ledger.json, rendered documents, gold.yaml
evaluation/
  queries.yaml      30 evaluation conversations
  extract_bundle.py extract a scenario into extracted.sqlite and score field accuracy
  run_eval.py       run configurations, score every turn, write logs, course.csv and summaries
  run_slice.py      Phase 1 slice runner
  results/          one folder per run
```

## Setup and usage

From the repository root:

```
python -m venv .venv
source .venv/bin/activate
pip install -e "project/code[dev,gemini]"
```

Then, from `project/`:

```
(cd code && pytest)                                              # unit tests (offline)
python data/generator/render.py data/dev/cafe_01                 # render the café scenario
python evaluation/extract_bundle.py data/dev/cafe_01 --llm reference   # offline pipeline check
python evaluation/run_eval.py data/dev/cafe_01 --llm scripted    # offline harness check

python evaluation/extract_bundle.py data/dev/cafe_01             # Gemini extraction -> extracted.sqlite
python evaluation/run_eval.py data/dev/cafe_01 --configs C1 C2 C3 C4   # Gemini answering, all configs
python evaluation/run_eval.py data/dev/cafe_01 --configs C1 C3 --queries Q01 Q04   # a subset
```

Each run writes `evaluation/results/<run id>/`: `log.jsonl` (every turn with its context, raw
reply and scores), `course.csv` (query, expected behavior, response, success, notes),
`summary.json` and `summary.md`.

## Data

All data is synthetic, generated ledger-first by `data/generator/`. No real business or personal
financial data is used. Each bundle in `data/dev/` and `data/test/` is one business over two to four
months: invoice PDFs, vendor messages, a bank-statement CSV, the owner's trusted vendor record, and
the ground-truth ledger. Generated SQLite files (`*.sqlite`) are not committed.

## Credentials

Model calls need an API key, which is never committed. Copy `code/.env.example` to
`project/code/.env` and set:

```
GEMINI_API_KEY=your_key_here
LLM_MODEL=optional-model-override
LLM_MIN_INTERVAL=optional-seconds-between-calls
```

`.env` is listed in `.gitignore`.

## Design rules the contracts enforce

- The extraction model returns strings and quotes only; code verifies each quote and normalizes
  money (Decimal), dates and payment terms.
- No tool takes a `business_id`; application code injects it. No tool writes.
- Document text reaches the answering model in C3/C4 only as fenced, untrusted quotes.
- Every response declares `ANSWER`, `CLARIFY` (exactly one question), `ABSTAIN`, or `WARN`
  (with a risk indicator), and `ANSWER`/`WARN` must cite at least one known record.
- Citations to unknown or other-business records are dropped; long digit runs are masked to
  the last four digits; invalid JSON is logged as a failure, never silently retried.
