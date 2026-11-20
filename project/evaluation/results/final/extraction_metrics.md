# NER-Style Extraction Precision, Recall, and F1

Each normalized field and each 4-tuple line item `(description, quantity, unit_price, line_total)` is scored as one entity unit (a partially correct value is both 1 FP and 1 FN).

## Held-out: landscaping_01 (13 documents)

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| vendor | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| invoice_number | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| issue_date | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| due_date | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| payment_terms | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| subtotal | 9 | 0 | 4 | 1.000 | 0.692 | 0.818 |
| tax | 9 | 0 | 4 | 1.000 | 0.692 | 0.818 |
| total | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| currency | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| remit_account_last4 | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| line_items | 25 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| **Overall (micro)** | **147** | **0** | **8** | **1.000** | **0.948** | **0.974** |

## Development pooled (cafe_01 + plumbing_01) (21 documents)

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| vendor | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| invoice_number | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| issue_date | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| due_date | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| payment_terms | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| subtotal | 15 | 0 | 6 | 1.000 | 0.714 | 0.833 |
| tax | 15 | 0 | 6 | 1.000 | 0.714 | 0.833 |
| total | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| currency | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| remit_account_last4 | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| line_items | 48 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| **Overall (micro)** | **246** | **0** | **12** | **1.000** | **0.953** | **0.976** |

## Development: cafe_01 (8 documents)

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| vendor | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| invoice_number | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| issue_date | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| due_date | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| payment_terms | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| subtotal | 6 | 0 | 2 | 1.000 | 0.750 | 0.857 |
| tax | 6 | 0 | 2 | 1.000 | 0.750 | 0.857 |
| total | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| currency | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| remit_account_last4 | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| line_items | 21 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| **Overall (micro)** | **97** | **0** | **4** | **1.000** | **0.960** | **0.980** |

## Development: plumbing_01 (13 documents)

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| vendor | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| invoice_number | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| issue_date | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| due_date | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| payment_terms | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| subtotal | 9 | 0 | 4 | 1.000 | 0.692 | 0.818 |
| tax | 9 | 0 | 4 | 1.000 | 0.692 | 0.818 |
| total | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| currency | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| remit_account_last4 | 13 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| line_items | 27 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| **Overall (micro)** | **149** | **0** | **8** | **1.000** | **0.949** | **0.974** |

## Real receipts: SROIE (626 documents)

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| company | 549 | 74 | 77 | 0.881 | 0.877 | 0.879 |
| date | 622 | 1 | 4 | 0.998 | 0.994 | 0.996 |
| total | 606 | 15 | 19 | 0.976 | 0.970 | 0.973 |
| **Overall (micro)** | **1777** | **90** | **100** | **0.952** | **0.947** | **0.949** |
