# Data

The scenario bundles are synthetic: nothing in them describes a real business or person. The only real documents used are 626 annotated receipts from ICDAR 2019 SROIE for the extraction check, which are stored in `data/real/` (gitignored, never committed).

```
generator/   render.py: turns a bundle's ledger.json into its documents
dev/         development bundles (used for building and tuning; e.g. cafe_01)
test/        frozen test bundles (never used for tuning; added later)
real/        SROIE source files and per-receipt outputs (gitignored, never committed)
```

## Bundle format

Each bundle folder holds one business:

| File | Contents |
|---|---|
| `ledger.json` | Ground truth: vendors, invoices, credits, bank rows, payment links, messages |
| `gold.yaml` | Hand-verified gold answers, values, and evidence IDs for the evaluation conversations |
| `invoices/*.pdf` | Text-native invoices, one layout per vendor |
| `invoices/*.fields.json` | Exactly what the renderer printed for each field, used to locate evidence |
| `credits/*.pdf` | Credit notes |
| `messages.jsonl` | Vendor emails and texts (no labels) |
| `bank.csv` | `txn_id,posted_on,amount,currency,descriptor` |
| `vendor_history.json` | The owner's trusted vendor record |

Render a bundle with `python data/generator/render.py data/dev/<bundle>` from `project/`.

## Real receipts (extraction check only)

The frozen invoice-header extraction prompt and schema are also scored on 626 real scanned receipts from ICDAR 2019 SROIE (transcripts and labels from <https://github.com/zzzDavid/ICDAR-2019-SROIE>, MIT license) alongside the synthetic café invoices. This measures whether extraction accuracy on synthetic invoices holds up on real documents for the three shared header fields: vendor name, date, and total.

Receipts are read from the dataset's own transcripts (`box/` and `key/`), so no images are sent to the model. Source files and per-receipt outputs live in `data/real/`, which is gitignored and never committed; only aggregate scores and receipt IDs are written to `evaluation/results/`.

To reproduce from `project/`:

```bash
git clone --depth 1 https://github.com/zzzDavid/ICDAR-2019-SROIE.git data/real/sroie_src
python evaluation/real_docs_check.py data/real/sroie_src/data --synthetic data/dev/cafe_01
# Optional: specify date order or re-score saved outputs without calling the model
python evaluation/real_docs_check.py data/real/sroie_src/data --date-order DMY --rescore data/real/runs/<run>.jsonl
```
