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

Phase 1 (vertical slice) in progress. Contracts, normalizers, SQLite store, gold loader and the
first two tools are implemented and tested. No model is called yet.

```
code/src/cashbooks/
  contracts/   typed interfaces between every stage (extraction, records, tools, response, eval)
  ingest/      PDF page text, bank CSV parser, bundle readers
  normalize/   money, dates, payment terms, vendor names, account fingerprints
  store/       SQLite schema, Store (scoped to one business), gold loader
  tools/       get_bill_status, list_open_bills, tool dispatch
evaluation/
  queries.yaml 30 evaluation conversations (draft until bundles and gold exist)
  run_slice.py Phase 1 slice: load a bundle, check the tools, measure C1 retrieval
```

## Setup and usage

From the repository root:

```
python -m venv .venv
source .venv/bin/activate
pip install -e "project/code[dev]"
```

Then, from `project/`:

```
(cd code && pytest)                                       # unit tests
python -m cashbooks.contracts.export                      # refresh code/schemas/
python data/generator/render.py data/dev/cafe_01          # render a scenario's documents
python evaluation/run_slice.py data/dev/cafe_01           # load it, check tools, measure retrieval
```

## Data

All data is synthetic, generated ledger-first by `data/generator/`. No real business or personal
financial data is used. Each bundle in `data/dev/` and `data/test/` is one business over two to four
months: invoice PDFs, vendor messages, a bank-statement CSV, the owner's trusted vendor record, and
the ground-truth ledger. Generated SQLite files (`*.sqlite`) are not committed.

## Credentials

Model calls need an API key, which is never committed. Create `project/code/.env` with:

```
LLM_API_KEY=your_key_here
LLM_MODEL=pinned-model-version
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
