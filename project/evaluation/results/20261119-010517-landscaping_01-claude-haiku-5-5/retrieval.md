# Retrieval Diagnosis (20261119-010517-landscaping_01-claude-haiku-5-5)

Source: `log.jsonl`.

## Overall mean recall@k and failure breakdown

| Config | Scored turns | Mean recall@k | Retrieval miss | Wrong reply type | Wrong value | Other |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 40 | 0.571 | 20 | 0 | 1 | 3 |
| C2 | 40 | 0.652 | 13 | 4 | 2 | 1 |

## Mean recall@k by question-type label

| Label | C1 | C2 |
| --- | --- | --- |
| lookup | 0.667 (n=4) | 0.792 (n=4) |
| aggregation | 0.542 (n=10) | 0.717 (n=10) |
| temporal | 0.528 (n=9) | 0.667 (n=9) |
| linking | 0.542 (n=12) | 0.667 (n=12) |
| comparison | 0.636 (n=11) | 0.591 (n=11) |
| dialogue | 0.409 (n=11) | 0.591 (n=11) |
| abstention | 1.000 (n=1) | 1.000 (n=1) |

## Retrieval misses by document type

| Config | Document type | Misses |
| --- | --- | --- |
| C1 | bank row | 5 |
| C1 | invoice | 19 |
| C1 | vendor record | 3 |
| C2 | bank row | 5 |
| C2 | invoice | 10 |
| C2 | vendor record | 3 |

## Retrieval miss details

| Config | Query | Turn | Missed doc | Doc type | Turn text |
| --- | --- | --- | --- | --- | --- |
| C1 | Q01 | 0 | inv_PL-314 | invoice | What bills are due in the next seven days? |
| C1 | Q02 | 0 | inv_PL-314 | invoice | How much do I owe Meadowlark Nursery & Sod as of September 30? |
| C1 | Q03 | 0 | inv_SUM-44 | invoice | Which invoices are overdue? |
| C1 | Q04 | 0 | txn_0514 | bank row | Did I already pay invoice MN-495? |
| C1 | Q07 | 0 | inv_IR-618 | invoice | Which bill should I verify before I pay it? |
| C1 | Q07 | 0 | vh_v_ironridge | vendor record | Which bill should I verify before I pay it? |
| C1 | Q10 | 0 | txn_0503 | bank row | Did I pay any invoice twice? |
| C1 | Q10 | 0 | txn_0506 | bank row | Did I pay any invoice twice? |
| C1 | Q13 | 0 | inv_IR-602 | invoice | Is the amount on IR-618 unusual for this vendor? |
| C1 | Q14 | 0 | inv_MN-495 | invoice | How much did I spend on grass seed in August? |
| C1 | Q16 | 0 | inv_PL-314 | invoice | List every unpaid Meadowlark invoice. |
| C1 | Q16 | 0 | inv_MN-512 | invoice | List every unpaid Meadowlark invoice. |
| C1 | Q17 | 1 | inv_RL-204 | invoice | What about the one before that? |
| C1 | Q17 | 2 | txn_0503 | bank row | Show me the payment. |
| C1 | Q19 | 1 | inv_PL-314 | invoice | Meadowlark. |
| C1 | Q19 | 1 | inv_MN-512 | invoice | Meadowlark. |
| C1 | Q19 | 2 | inv_MN-480 | invoice | Only the overdue part. |
| C1 | Q19 | 2 | inv_CT-88 | invoice | Only the overdue part. |
| C1 | Q20 | 1 | vh_v_ironridge | vendor record | Then draft a verification message. |
| C1 | Q21 | 1 | inv_MN-495 | invoice | Was the second invoice paid? |
| C1 | Q22 | 1 | inv_SUM-44 | invoice | Compared with the previous invoice? |
| C1 | Q22 | 2 | vh_v_ironridge | vendor record | Could it be a typo? |
| C1 | Q25 | 0 | txn_0516 | bank row | What remains due on PL-314 after the payment and credit? |
| C1 | Q27 | 0 | inv_PL-314 | invoice | Show all invoices from Meadowlark after it changed its legal name. |
| C1 | Q27 | 0 | inv_MN-512 | invoice | Show all invoices from Meadowlark after it changed its legal name. |
| C1 | Q28 | 0 | inv_BF-301 | invoice | What is my total outstanding? |
| C1 | Q28 | 0 | inv_IR-618 | invoice | What is my total outstanding? |
| C2 | Q01 | 0 | inv_PL-314 | invoice | What bills are due in the next seven days? |
| C2 | Q03 | 0 | inv_SUM-44 | invoice | Which invoices are overdue? |
| C2 | Q04 | 0 | txn_0514 | bank row | Did I already pay invoice MN-495? |
| C2 | Q07 | 0 | inv_IR-618 | invoice | Which bill should I verify before I pay it? |
| C2 | Q07 | 0 | vh_v_ironridge | vendor record | Which bill should I verify before I pay it? |
| C2 | Q10 | 0 | txn_0503 | bank row | Did I pay any invoice twice? |
| C2 | Q10 | 0 | txn_0506 | bank row | Did I pay any invoice twice? |
| C2 | Q14 | 0 | inv_MN-495 | invoice | How much did I spend on grass seed in August? |
| C2 | Q17 | 2 | txn_0503 | bank row | Show me the payment. |
| C2 | Q20 | 1 | vh_v_ironridge | vendor record | Then draft a verification message. |
| C2 | Q22 | 1 | inv_IR-618 | invoice | Compared with the previous invoice? |
| C2 | Q22 | 1 | inv_SUM-44 | invoice | Compared with the previous invoice? |
| C2 | Q22 | 2 | vh_v_ironridge | vendor record | Could it be a typo? |
| C2 | Q25 | 0 | txn_0516 | bank row | What remains due on PL-314 after the payment and credit? |
| C2 | Q27 | 0 | inv_PL-314 | invoice | Show all invoices from Meadowlark after it changed its legal name. |
| C2 | Q27 | 0 | inv_MN-512 | invoice | Show all invoices from Meadowlark after it changed its legal name. |
| C2 | Q28 | 0 | inv_BF-301 | invoice | What is my total outstanding? |
| C2 | Q28 | 0 | inv_IR-618 | invoice | What is my total outstanding? |

## Per-turn recall@k

| Config | Query | Turn | k | Recall@k | Success | Failure category |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | Q01 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q02 | 0 | 8 | 0.75 | False | retrieval miss |
| C1 | Q03 | 0 | 8 | 0.67 | False | retrieval miss |
| C1 | Q04 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q05 | 0 | 8 | 1.00 | True | - |
| C1 | Q06 | 0 | 8 | 1.00 | True | - |
| C1 | Q07 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q08 | 0 | 8 | 1.00 | True | - |
| C1 | Q09 | 0 | 8 | 1.00 | True | - |
| C1 | Q10 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q11 | 0 | 8 | 1.00 | True | - |
| C1 | Q12 | 0 | 8 | 1.00 | True | - |
| C1 | Q13 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q14 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q15 | 0 | 8 | 1.00 | True | - |
| C1 | Q16 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q17 | 0 | 8 | n/a | False | other |
| C1 | Q17 | 1 | 8 | 0.00 | False | retrieval miss |
| C1 | Q17 | 2 | 8 | 0.00 | False | retrieval miss |
| C1 | Q18 | 0 | 8 | n/a | True | - |
| C1 | Q18 | 1 | 8 | 1.00 | True | - |
| C1 | Q18 | 2 | 8 | 1.00 | True | - |
| C1 | Q19 | 0 | 8 | n/a | False | other |
| C1 | Q19 | 1 | 8 | 0.50 | False | retrieval miss |
| C1 | Q19 | 2 | 8 | 0.00 | False | retrieval miss |
| C1 | Q20 | 0 | 8 | n/a | False | other |
| C1 | Q20 | 1 | 8 | 0.00 | False | retrieval miss |
| C1 | Q21 | 1 | 8 | 0.50 | False | retrieval miss |
| C1 | Q21 | 2 | 8 | 1.00 | True | - |
| C1 | Q22 | 0 | 8 | n/a | True | - |
| C1 | Q22 | 1 | 8 | 0.50 | False | retrieval miss |
| C1 | Q22 | 2 | 8 | 0.00 | False | retrieval miss |
| C1 | Q23 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | Q24 | 0 | 8 | 1.00 | True | - |
| C1 | Q25 | 0 | 8 | 0.67 | False | retrieval miss |
| C1 | Q26 | 0 | 8 | 1.00 | True | - |
| C1 | Q27 | 0 | 8 | 0.33 | False | retrieval miss |
| C1 | Q28 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q29 | 0 | 8 | n/a | True | - |
| C1 | Q30 | 0 | 8 | 1.00 | True | - |
| C2 | Q01 | 0 | 8 | 0.50 | False | retrieval miss |
| C2 | Q02 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | Q03 | 0 | 8 | 0.67 | False | retrieval miss |
| C2 | Q04 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q05 | 0 | 8 | 1.00 | True | - |
| C2 | Q06 | 0 | 8 | 1.00 | True | - |
| C2 | Q07 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q08 | 0 | 8 | 1.00 | True | - |
| C2 | Q09 | 0 | 8 | 1.00 | True | - |
| C2 | Q10 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q11 | 0 | 8 | 1.00 | True | - |
| C2 | Q12 | 0 | 8 | 0.50 | True | - |
| C2 | Q13 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q14 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q15 | 0 | 8 | 1.00 | True | - |
| C2 | Q16 | 0 | 8 | 1.00 | True | - |
| C2 | Q17 | 0 | 8 | n/a | True | - |
| C2 | Q17 | 1 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q17 | 2 | 8 | 0.00 | False | retrieval miss |
| C2 | Q18 | 0 | 8 | n/a | False | other |
| C2 | Q18 | 1 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q18 | 2 | 8 | 1.00 | True | - |
| C2 | Q19 | 0 | 8 | n/a | True | - |
| C2 | Q19 | 1 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | Q19 | 2 | 8 | 0.50 | True | - |
| C2 | Q20 | 0 | 8 | n/a | True | - |
| C2 | Q20 | 1 | 8 | 0.00 | False | retrieval miss |
| C2 | Q21 | 1 | 8 | 1.00 | True | - |
| C2 | Q21 | 2 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q22 | 0 | 8 | n/a | True | - |
| C2 | Q22 | 1 | 8 | 0.00 | False | retrieval miss |
| C2 | Q22 | 2 | 8 | 0.00 | False | retrieval miss |
| C2 | Q23 | 0 | 8 | 1.00 | True | - |
| C2 | Q24 | 0 | 8 | 1.00 | True | - |
| C2 | Q25 | 0 | 8 | 0.67 | False | retrieval miss |
| C2 | Q26 | 0 | 8 | 1.00 | True | - |
| C2 | Q27 | 0 | 8 | 0.33 | False | retrieval miss |
| C2 | Q28 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q29 | 0 | 8 | n/a | True | - |
| C2 | Q30 | 0 | 8 | 1.00 | True | - |

## Document-level retrieval at rank (QA lecture)

| Config | Turns | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 34 | 0.206 | 0.176 | 0.129 | 0.132 | 0.176 | 0.368 | 0.407 | 0.571 | 0.364 |
| C2 | 34 | 0.265 | 0.255 | 0.200 | 0.158 | 0.213 | 0.414 | 0.547 | 0.652 | 0.441 |
