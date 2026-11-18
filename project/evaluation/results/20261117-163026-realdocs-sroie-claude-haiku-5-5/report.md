# Extraction on real receipts vs synthetic invoices

Model `claude-haiku-5-5`, prompt `extract_invoice_header_v1.md`, 626 SROIE receipts, 3 failed calls.

| Field | Synthetic café invoices | Real receipts: value read | Real receipts: after normalization |
| --- | --- | --- | --- |
| Vendor name | 8/8 (100%) | 549/626 (88%) exact, 591/626 (94%) lenient | (no normalization) |
| Date | 8/8 (100%) | 620/626 (99%) | 50/626 (8%) |
| Total | 8/8 (100%) | 606/625 (97%) | 606/625 (97%) |

Dates the month-first normalizer turned into a wrong but valid date (not rejected): 144/626 (23%).

Quotes found verbatim in the receipt text: 1866/1867. Tokens: 2139038 in, 517983 out.
