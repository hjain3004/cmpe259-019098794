# Retrieval Diagnosis (20261118-231330-bakery_01-claude-haiku-5-5)

Source: `log.jsonl`.

## Overall mean recall@k and failure breakdown

| Config | Scored turns | Mean recall@k | Retrieval miss | Wrong reply type | Wrong value | Other |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 27 | 0.865 | 5 | 2 | 1 | 4 |
| C2 | 27 | 0.913 | 3 | 3 | 3 | 3 |

## Mean recall@k by question-type label

| Label | C1 | C2 |
| --- | --- | --- |
| lookup | 0.500 (n=1) | 1.000 (n=1) |
| aggregation | 0.786 (n=7) | 1.000 (n=7) |
| temporal | 0.812 (n=8) | 0.875 (n=8) |
| linking | 0.889 (n=12) | 0.931 (n=12) |
| comparison | 0.917 (n=6) | 0.917 (n=6) |
| dialogue | 0.931 (n=12) | 0.847 (n=12) |
| abstention | 1.000 (n=1) | 1.000 (n=1) |

## Retrieval misses by document type

| Config | Document type | Misses |
| --- | --- | --- |
| C1 | invoice | 5 |
| C1 | vendor record | 1 |
| C2 | invoice | 2 |
| C2 | vendor record | 1 |

## Retrieval miss details

| Config | Query | Turn | Missed doc | Doc type | Turn text |
| --- | --- | --- | --- | --- | --- |
| C1 | D101 | 0 | inv_MC-220 | invoice | Which bills are due in the next seven days? |
| C1 | D102 | 0 | inv_GC-118 | invoice | How much do I owe Golden Crust Wholesale LLC across all open bills? |
| C1 | D102 | 0 | inv_GC-125 | invoice | How much do I owe Golden Crust Wholesale LLC across all open bills? |
| C1 | D111 | 0 | inv_GC-118 | invoice | How much did I spend on flour in August? |
| C1 | D113 | 2 | vh_v_packaging | vendor record | What about the other INV-204—can I pay it to the account printed on it? |
| C1 | D116 | 1 | inv_INV-204--goldencrust | invoice | List all unpaid bills from them. |
| C2 | D113 | 2 | vh_v_packaging | vendor record | What about the other INV-204—can I pay it to the account printed on it? |
| C2 | D116 | 1 | inv_INV-204--goldencrust | invoice | List all unpaid bills from them. |
| C2 | D117 | 1 | inv_SB-305 | invoice | Solstice uses day-month-year. |

## Per-turn recall@k

| Config | Query | Turn | k | Recall@k | Success | Failure category |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | D101 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | D102 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | D103 | 0 | 8 | 1.00 | True | - |
| C1 | D104 | 0 | 8 | 1.00 | True | - |
| C1 | D105 | 0 | 8 | n/a | False | other |
| C1 | D106 | 0 | 8 | 1.00 | False | other |
| C1 | D107 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | D108 | 0 | 8 | n/a | True | - |
| C1 | D109 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | D110 | 0 | 8 | 1.00 | True | - |
| C1 | D111 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | D112 | 0 | 8 | n/a | True | - |
| C1 | D113 | 0 | 8 | n/a | True | - |
| C1 | D113 | 1 | 8 | 1.00 | True | - |
| C1 | D113 | 2 | 8 | 0.50 | False | retrieval miss |
| C1 | D114 | 0 | 8 | 1.00 | True | - |
| C1 | D114 | 1 | 8 | 1.00 | True | - |
| C1 | D114 | 2 | 8 | 1.00 | True | - |
| C1 | D115 | 0 | 8 | 1.00 | True | - |
| C1 | D115 | 1 | 8 | 1.00 | True | - |
| C1 | D116 | 0 | 8 | 1.00 | True | - |
| C1 | D116 | 1 | 8 | 0.67 | False | retrieval miss |
| C1 | D116 | 2 | 8 | 1.00 | True | - |
| C1 | D117 | 0 | 8 | n/a | False | other |
| C1 | D117 | 1 | 8 | 1.00 | True | - |
| C1 | D118 | 0 | 8 | n/a | False | other |
| C1 | D118 | 1 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | D101 | 0 | 8 | 1.00 | True | - |
| C2 | D102 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D103 | 0 | 8 | 1.00 | True | - |
| C2 | D104 | 0 | 8 | 1.00 | True | - |
| C2 | D105 | 0 | 8 | n/a | True | - |
| C2 | D106 | 0 | 8 | 1.00 | True | - |
| C2 | D107 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D108 | 0 | 8 | n/a | False | other |
| C2 | D109 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | D110 | 0 | 8 | 1.00 | True | - |
| C2 | D111 | 0 | 8 | 1.00 | True | - |
| C2 | D112 | 0 | 8 | n/a | True | - |
| C2 | D113 | 0 | 8 | n/a | True | - |
| C2 | D113 | 1 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D113 | 2 | 8 | 0.50 | False | retrieval miss |
| C2 | D114 | 0 | 8 | 1.00 | True | - |
| C2 | D114 | 1 | 8 | 1.00 | True | - |
| C2 | D114 | 2 | 8 | 1.00 | True | - |
| C2 | D115 | 0 | 8 | 1.00 | True | - |
| C2 | D115 | 1 | 8 | 1.00 | True | - |
| C2 | D116 | 0 | 8 | 1.00 | True | - |
| C2 | D116 | 1 | 8 | 0.67 | False | retrieval miss |
| C2 | D116 | 2 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | D117 | 0 | 8 | n/a | False | other |
| C2 | D117 | 1 | 8 | 0.00 | False | retrieval miss |
| C2 | D118 | 0 | 8 | n/a | False | other |
| C2 | D118 | 1 | 8 | 1.00 | False | evidence retrieved, wrong reply type |

## Document-level retrieval at rank (QA lecture)

| Config | Turns | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 21 | 0.524 | 0.381 | 0.343 | 0.220 | 0.329 | 0.583 | 0.841 | 0.865 | 0.683 |
| C2 | 21 | 0.429 | 0.365 | 0.324 | 0.238 | 0.258 | 0.516 | 0.734 | 0.913 | 0.607 |
