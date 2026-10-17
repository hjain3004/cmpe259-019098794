# Data

The scenario bundles are synthetic: nothing in them describes a real business or person. The only real documents used are a sample of annotated invoices from DocILE, which are not stored in this repository.

```
generator/   render.py: turns a bundle's ledger.json into its documents
dev/         development bundles (used for building and tuning)
test/        frozen test bundles (never used for tuning; added later)
real/        IDs of the real invoices used for the extraction check (documents not committed)
```

## Bundle format

Each bundle folder holds one business:

| File | Contents |
|---|---|
| `ledger.json` | Ground truth: vendors, invoices, credits, bank rows, payment links, messages |
| `invoices/*.pdf` | Text-native invoices, one layout per vendor |
| `invoices/*.fields.json` | Exactly what the renderer printed for each field, used to locate evidence |
| `credits/*.pdf` | Credit notes |
| `messages.jsonl` | Vendor emails and texts (no labels) |
| `bank.csv` | `txn_id,posted_on,amount,currency,descriptor` |
| `vendor_history.json` | The owner's trusted vendor record |

Render a bundle with `python data/generator/render.py data/dev/<bundle>` from `project/`.

## Real invoices (extraction check only)

The extraction step is also scored on 40 real annotated invoices from the DocILE benchmark
(Šimsa et al., ICDAR 2023). Synthetic invoices are cleaner than real ones, and this check measures
how much that matters.

To reproduce it:

1. Request access through the form on <https://docile.rossum.ai/> and download the annotated set
   following the instructions in <https://github.com/rossumai/docile>.
2. Place it outside the repository, or in `data/real/docile/`, which is ignored by git.
3. The document IDs used are listed in `data/real/docile_sample.txt`.

DocILE documents and annotations are never committed. Only the sample IDs and aggregate scores are.
