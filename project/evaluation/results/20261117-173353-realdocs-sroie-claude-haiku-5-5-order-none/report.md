# Extraction on real receipts vs synthetic invoices

Model `claude-haiku-5-5`, prompt `extract_invoice_header_v1.md`, 626 SROIE receipts, 3 failed calls.

| Field | Synthetic café invoices | Real receipts: value read | Real receipts: after normalization |
| --- | --- | --- | --- |
| Vendor name | 8/8 (100%) | 549/626 (88%) exact, 591/626 (94%) lenient | (no normalization) |
| Date | 8/8 (100%) | 622/626 (99%) | 421/626 (67%) |
| Total | 8/8 (100%) | 606/625 (97%) | 606/625 (97%) |

Date order given to the parser: none (unknown). Flagged as ambiguous instead of guessed: 201/626 (32%). Turned into a wrong but valid date: 1/626 (0%).

Quotes found verbatim in the receipt text: 1866/1867. Tokens: 2139038 in, 517983 out.
