# CashBooks Assist

A read-only assistant that answers small-business questions about vendor bills, credit notes, bank payments, and vendor messages. It reconciles invoices against bank rows, flags unverified payment-detail changes, and surfaces attention items without ever executing payments, sending messages, or modifying records.

## Target users

Owner-operated small businesses (1–20 employees, no dedicated accounts-payable staff) who need to check what is owed, verify whether a payment cleared, and spot risky bank-change requests before paying.

## How to run it

Requires Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "project/code[dev,claude,demo]"
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

### Usage

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

# 5. Compute paired McNemar tests, conversation-clustered bootstrap CIs, and MDE planning
python evaluation/stats.py evaluation/results/<run_id>/rescored --plan 60 90 120

# 6. Run retrieval diagnosis (C1 vs C2) and attention-item evaluation
python evaluation/retrieval_diagnosis.py evaluation/results/<run_id>
python evaluation/attention_eval.py

# 7. Run the safety suites (offline scripted, or real model)
python evaluation/run_safety.py --llm scripted
python evaluation/run_safety.py --configs C1 C2 C3 C4
python evaluation/run_safety.py --safety-file evaluation/safety_quorum.yaml --configs C1 C2 C3 C4

# 8. Run the real-document extraction check on 626 SROIE receipts
git clone --depth 1 https://github.com/zzzDavid/ICDAR-2019-SROIE.git data/real/sroie_src
python evaluation/real_docs_check.py data/real/sroie_src/data --synthetic data/dev/cafe_01

# 9. Scorer audit (sample 40 stratified turns, then compute human agreement)
python evaluation/audit_sample.py sample evaluation/results/<run_id>
python evaluation/audit_sample.py report --csv evaluation/scorer_audit.csv
```

Launch the interactive Streamlit chat demo from the repository root:

```bash
streamlit run project/demo/app.py
```

## Data sources and tools

- **Synthetic scenario bundles:** Generated ledger-first from `ledger.json` by `data/generator/render.py` into invoice PDFs, vendor messages (`messages.jsonl`), bank statement rows (`bank.csv`), trusted vendor history (`vendor_history.json`), and ground truth (`gold.yaml`). Development bundles are `data/dev/cafe_01` and `data/dev/plumbing_01`. The test bundle `data/test/landscaping_01` is held out from tuning and frozen before any run, but generated with the same templates as the development bundles.
- **Real-document extraction check:** `evaluation/real_docs_check.py` scores header extraction on 626 public receipts from ICDAR 2019 SROIE stored in `data/real/` (gitignored).
- **Seven read-only tools** (all business-scoped in code; no tool writes or takes `business_id`):
  1. `list_open_bills` — open, partial, or settled bills with exact remaining balances
  2. `get_bill_status` — status, due dates, line items, PO, linked payments, credits, and message conflicts
  3. `match_payments` — confirmed and candidate bank matches by invoice, transaction ID, amount, or date
  4. `sum_amount_due` — total remaining per currency with contributing bills
  5. `compare_vendor_payment_details` — compares invoice remit-to details against the owner's verified record
  6. `summarize_purchases` — quantities and spend from line items
  7. `get_source_evidence` — verified source quotes fenced as untrusted data

## Configurations compared

All five configurations use the same answering model (`claude-haiku-5-5` via the Anthropic Messages API), response contract, post-processing, and deterministic scorer:

| Config | What the answering model receives |
|---|---|
| `C0` | Full corpus: all raw document chunks in a stable order |
| `C1` | Top-$k$ ($k=8$) BM25-retrieved chunks of raw invoices, messages, and bank rows |
| `C2` | Top-$k$ ($k=8$) BM25-retrieved serialized extracted records |
| `C3` | Seven read-only deterministic tools over the extracted SQLite store |
| `C4` | Same seven tools over hand-verified gold records (isolates extraction error) |

## How it was evaluated

Every reply must follow a strict JSON contract (`ANSWER`, `CLARIFY`, `ABSTAIN`, or `WARN`) and pass deterministic post-processing (dropping unknown citations, masking 6+ digit runs to the last four digits). Scoring checks answerability, exact money to the cent, dates, statuses, document-level evidence recall/precision, and negation-aware `must_not` rules, with no LLM judge. Statistical comparisons use two-sided exact McNemar tests and 10,000-resample conversation-clustered bootstrap confidence intervals (`evaluation/stats.py`), alongside a blinded 40-turn scorer audit (`evaluation/review/`).

### Development results (`evaluation/results/final/report_dev.md`)

Pooled across 4 runs on `cafe_01` and `plumbing_01` (2 repeats each, 136 scored turns per configuration):

| Scope | Config | Turn success | Conversation success | Parse rate |
| --- | --- | --- | --- | --- |
| cafe_01 | C0 | 35/56 (62%) | 26/42 (62%) | 53/56 (95%) |
| cafe_01 | C1 | 25/56 (45%) | 13/42 (31%) | 56/56 (100%) |
| cafe_01 | C2 | 29/56 (52%) | 16/42 (38%) | 56/56 (100%) |
| cafe_01 | C3 | 38/56 (68%) | 26/42 (62%) | 52/56 (93%) |
| cafe_01 | C4 | 41/56 (73%) | 29/42 (69%) | 56/56 (100%) |
| plumbing_01 | C0 | 47/80 (59%) | 33/60 (55%) | 74/80 (92%) |
| plumbing_01 | C1 | 29/80 (36%) | 22/60 (37%) | 78/80 (98%) |
| plumbing_01 | C2 | 42/80 (52%) | 28/60 (47%) | 80/80 (100%) |
| plumbing_01 | C3 | 46/80 (57%) | 31/60 (52%) | 78/80 (98%) |
| plumbing_01 | C4 | 44/80 (55%) | 29/60 (48%) | 79/80 (99%) |
| **Pooled** | **C0** | **82/136 (60%)** | **59/102 (58%)** | **127/136 (93%)** |
| **Pooled** | **C1** | **54/136 (40%)** | **35/102 (34%)** | **134/136 (99%)** |
| **Pooled** | **C2** | **71/136 (52%)** | **44/102 (43%)** | **136/136 (100%)** |
| **Pooled** | **C3** | **84/136 (62%)** | **57/102 (56%)** | **130/136 (96%)** |
| **Pooled** | **C4** | **85/136 (62%)** | **58/102 (57%)** | **135/136 (99%)** |

Pooled error rates and grounding:

| Config | Unwarranted-warning rate | Over-abstention rate | Citation recall | Citation precision |
| --- | --- | --- | --- | --- |
| C0 | 28/106 (26%) | 1/92 (1%) | 0.998 | 0.427 |
| C1 | 29/106 (27%) | 27/92 (29%) | 0.604 | 0.303 |
| C2 | 32/106 (30%) | 18/92 (20%) | 0.757 | 0.405 |
| C3 | 24/106 (23%) | 1/92 (1%) | 0.869 | 0.617 |
| C4 | 29/106 (27%) | 1/92 (1%) | 0.842 | 0.603 |

On pooled development turns, `C3` outperforms `C1` by `+22.1%` (`42:12` discordant, exact McNemar `p = 0.000`, 95% bootstrap CI `[+9.6%, +34.5%]`) and `C2` outperforms `C1` by `+12.5%` (`23:6`, `p = 0.002`), while `C3` and `C4` tie (`-0.7%`, `9:10`, `p = 1.000`).

### Final and held-out results

- [FINAL TABLE: overall summary from evaluation/results/final/SUMMARY.md]
- [FINAL TABLE: all-bundles comparison from evaluation/results/final/report_all.md]
- [FINAL TABLE: held-out landscaping_01 results from evaluation/results/final/report_heldout.md]
- [FINAL TABLE: pooled retrieval diagnosis from evaluation/results/final/retrieval.md]
- [FINAL TABLE: blinded scorer audit agreement from evaluation/results/final/scorer_audit.md]

## Safety and robustness tests

The safety suite (`evaluation/safety.yaml` and `evaluation/safety_quorum.yaml`) pairs each attack with a benign control across direct injection (S01), indirect injection (S02), unverified bank-change requests (S03), conflicting authority (S05), action requests (S07), secret extraction (S08), sensitive-data masking (S09), and red-team memo/remit attacks (S11, S12). Attack wordings for S11 and S12 are adapted from Quorum (Drexathon 2026), co-built with Dhruv J., and selected deterministically as described in `evaluation/safety_sources/`.

- [SAFETY TABLE: final safety and red-team results from evaluation/results/final/safety.md]

## Peer testing and demo

See [`docs/peer_testing.md`](docs/peer_testing.md) for the 15-minute classmate testing script, feedback form, and results template. Sessions saved by `demo/app.py` to `demo/sessions/` can be converted into draft unseen test questions with `python evaluation/peer_queries.py`.

- [PEER TESTING: classmate testing results]
- [DEMO RECORDING: link to demo video]

## Limitations

- **Synthetic primary corpus:** End-to-end reconciliation, multi-turn dialogue, and safety are evaluated on synthetic bundles; `landscaping_01` is held out from tuning and frozen before any run, but generated with the same templates as the development bundles. The real-document check covers header extraction on retail receipts (SROIE) rather than multi-page supplier invoices.
- **Single answering model:** All reported configurations use `claude-haiku-5-5`, and the Anthropic Messages API exposes no temperature parameter, so individual runs have small turn-to-turn variance.
- **Read-only scope:** The assistant never initiates payments, sends messages, or edits records; it flags discrepancies and recommends independent verification through the contact on file.
- **Over-warning on benign bills:** Even with tools (`C3`), the model still issues unwarranted warnings on 23% of benign `ANSWER`/`CLARIFY` turns.

## Future improvements

- **Multi-turn clarification handling:** Improve follow-up resolution on underspecified turns where tool-based configurations still trail single-turn accuracy.
- **Reducing exaggerated safety:** Calibrate warning triggers so verified invoices without discrepancies receive `ANSWER` rather than `WARN`.
- **Independent real-invoice evaluation:** Score full-pipeline extraction and reconciliation on multi-page supplier invoices when linked real data is available.
- **Broader corpus scaling:** Test retrieval and full-corpus `C0` under larger invoice volumes and more hard-negative distractors.

## Documents

- [`proposal/proposal.pdf`](proposal/proposal.pdf): submitted proposal (11 Sep 2026), unchanged
- [`docs/design.md`](docs/design.md): system design and evaluation plan
- [`docs/decisions.md`](docs/decisions.md): dated decision log (D1–D27)
- [`docs/references.md`](docs/references.md): reading list and dataset notes; BibTeX in [`docs/references.bib`](docs/references.bib)
- [`docs/peer_testing.md`](docs/peer_testing.md): classmate testing kit
- [`checkins/`](checkins/): check-in reports
