# Data

All data is synthetic. Nothing here describes a real business or person.

```
generator/   render.py: turns a bundle's ledger.json into its documents
dev/         development bundles (used for building and tuning)
test/        frozen test bundles (never used for tuning; added later)
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
