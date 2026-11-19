# CashBooks Assist

A read-only LLM assistant that answers a small-business owner's questions about vendor bills, credit notes, bank payments, and vendor messages. It is also a controlled experiment asking: **on multi-document financial reconciliation and dialogue, how much do structured extraction and read-only deterministic tools improve accuracy, grounding, and prompt-injection robustness over putting raw documents or BM25 chunks directly in the prompt?**

## Configurations

All five configurations use the same answering model (`claude-haiku-5-5` via the Anthropic Messages API), response contract, post-processing, and deterministic scorer:

| Config | What the answering model receives |
|---|---|
| `C0` | Full corpus: all raw document chunks in a stable order |
| `C1` | Top-$k$ ($k=8$) BM25-retrieved chunks of raw invoices, messages, and bank rows |
| `C2` | Top-$k$ ($k=8$) BM25-retrieved serialized extracted records |
| `C3` | Seven read-only deterministic tools over the extracted SQLite store |
| `C4` | Same seven tools over hand-verified gold records (isolates extraction error) |

## Repository layout

```
project/
  code/src/cashbooks/
    contracts/   typed Pydantic interfaces (extraction, records, tools, response, eval, safety)
    ingest/      PDF page text, bank CSV parser, bundle readers
    normalize/   money (Decimal), dates, payment terms, vendor names, account fingerprints
    store/       SQLite schema, business-scoped Store, gold loader
    tools/       seven read-only tools, payment matching, tool dispatch
    extract/     model extraction into typed records; reference extractor for offline checks
    configs/     BM25 retrieval (C1, C2), full-corpus context (C0), and C0–C4 wiring
    llm/         Anthropic Claude client, Gemini client, scripted stand-in for tests
    demo/        chat session wrapper for the Streamlit UI
    scoring.py   deterministic turn scoring, grounding/usability metrics, run logs
    safety.py    deterministic safety turn scoring and reporting
  code/tests/    pytest suite
  prompts/       versioned system and extraction prompts
  data/
    generator/   render.py: renders a ledger.json into invoice PDFs, messages, bank CSV, vendor history
    dev/         development bundles (e.g. cafe_01)
    real/        SROIE receipts and per-receipt outputs (gitignored, never committed)
  evaluation/
    queries.yaml       evaluation conversations
    safety.yaml        Phase 1 safety suite (S01–S03, S05, S07–S09)
    safety_quorum.yaml red-team indirect-injection and account-swap variants
    extract_bundle.py  extract a bundle into extracted.sqlite and score field accuracy
    run_eval.py        run C0–C4 on a bundle, score turns, write logs and summaries
    rescore.py         re-score saved replies without calling the model
    run_safety.py      run safety suites across C1–C4
    real_docs_check.py score header extraction on 626 SROIE receipts vs. synthetic invoices
    audit_sample.py    stratified 40-turn audit sampler and human-agreement kappa reporter
    peer_queries.py    extract unseen questions from saved demo sessions
    results/           one folder per run
  demo/
    app.py             Streamlit chat interface
    sessions/          saved peer-testing session logs (gitignored except .gitkeep)
  docs/                design.md, decisions.md, references.md, references.bib, peer_testing.md
```

## Setup

Requires Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "project/code[dev]"
```

Run the offline test suite from `project/code/`:

```bash
cd project/code && pytest
```

### Credentials and model selection

Model calls use the Anthropic Messages API (`claude-haiku-5-5` by default). Copy `project/code/.env.example` to `project/code/.env` (never committed) and set:

```bash
ANTHROPIC_API_KEY=your_key_here
# Optional model override (default: claude-haiku-5-5):
# LLM_MODEL=claude-haiku-5-5
```

You can also override the model per run with `--model <model_id>` on the evaluation scripts.

## Usage

Run the commands below from `project/`:

```bash
# 1. Render a synthetic bundle from its ledger.json
python data/generator/render.py data/dev/cafe_01

# 2. Extract records into extracted.sqlite (offline reference check, or real Claude extraction)
python evaluation/extract_bundle.py data/dev/cafe_01 --llm reference
python evaluation/extract_bundle.py data/dev/cafe_01

# 3. Run the evaluation (offline scripted dry run, or real model across C0–C4)
python evaluation/run_eval.py data/dev/cafe_01 --llm scripted
python evaluation/run_eval.py data/dev/cafe_01 --configs C0 C1 C2 C3 C4
python evaluation/run_eval.py data/dev/cafe_01 --configs C1 C3 --queries Q01 Q04

# 4. Re-score saved replies without calling the model (writes to <run>/rescored/)
python evaluation/rescore.py evaluation/results/<run_id> data/dev/cafe_01

# 5. Run the safety suites (offline scripted, or real model)
python evaluation/run_safety.py --llm scripted
python evaluation/run_safety.py --configs C1 C2 C3 C4
python evaluation/run_safety.py --safety-file evaluation/safety_quorum.yaml --configs C1 C2 C3 C4

# 6. Run the real-document extraction check on 626 SROIE receipts
git clone --depth 1 https://github.com/zzzDavid/ICDAR-2019-SROIE.git data/real/sroie_src
python evaluation/real_docs_check.py data/real/sroie_src/data --synthetic data/dev/cafe_01

# 7. Scorer audit (sample 40 stratified turns, then compute human agreement)
python evaluation/audit_sample.py sample evaluation/results/<run_id>
python evaluation/audit_sample.py report --csv evaluation/scorer_audit.csv
```

Launch the interactive chat demo from the repository root:

```bash
streamlit run project/demo/app.py
```

## Data

All scenario bundles (`data/dev/`) are synthetic, generated ledger-first by `data/generator/render.py`: invoice PDFs, vendor messages, a bank-statement CSV, the owner's trusted vendor record, and `gold.yaml`. No real business or personal financial data is used. For the extraction check only, `evaluation/real_docs_check.py` scores header extraction on 626 public receipts from ICDAR 2019 SROIE stored in `data/real/` (gitignored). See [`data/README.md`](data/README.md).

## Evaluation

Each `run_eval.py` run writes `evaluation/results/<run_id>/`:
- `log.jsonl`: one `LogRow` per turn with context/tool calls, raw reply, and deterministic scores
- `course.csv`: `configuration`, `query_id`, `turn`, `query`, `expected_behavior`, `response`, `success`, `notes`
- `summary.json` and `summary.md`: turn success, conversation success, answer-type accuracy, exact-value accuracy, mean evidence recall/precision, mean citations, median/P90 answer word count, share under 120 words, latency, and tokens

Each `run_safety.py` run writes `log.jsonl`, `safety.csv`, `summary.json`, and `summary.md` reporting Benign Utility, Utility Under Attack, Attack Success Rate, and a per-test pass/fail grid.

## Results

Final results will be added after the final runs.

## Peer testing

See [`docs/peer_testing.md`](docs/peer_testing.md) for the 15-minute classmate testing script, feedback form, and results template. Sessions saved by `demo/app.py` to `demo/sessions/` can be converted into draft unseen test questions with:

```bash
python evaluation/peer_queries.py
```

## Limitations

- **Synthetic primary corpus:** End-to-end reconciliation, multi-turn dialogue, and safety are evaluated on synthetic bundles; the real-document check covers header extraction on retail receipts (SROIE) rather than multi-page supplier invoices.
- **Single answering model:** All reported configurations use `claude-haiku-5-5`, and the Anthropic Messages API exposes no temperature parameter, so individual runs have small turn-to-turn variance.
- **Read-only scope:** The assistant never initiates payments, sends messages, or edits records; it flags discrepancies and recommends independent verification through the contact on file.
- **Safety wording:** Attack wordings for S11 and S12 are adapted from Quorum (Drexathon 2026), co-built with Dhruv J., and selected deterministically as described in `evaluation/safety_sources/`.

## Documents

- [`proposal/proposal.pdf`](proposal/proposal.pdf): submitted proposal (11 Sep 2026), unchanged
- [`docs/design.md`](docs/design.md): system design and evaluation plan
- [`docs/decisions.md`](docs/decisions.md): dated decision log (D1–D23)
- [`docs/references.md`](docs/references.md): reading list and dataset notes; BibTeX in [`docs/references.bib`](docs/references.bib)
- [`docs/peer_testing.md`](docs/peer_testing.md): classmate testing kit
- [`checkins/`](checkins/): check-in reports
