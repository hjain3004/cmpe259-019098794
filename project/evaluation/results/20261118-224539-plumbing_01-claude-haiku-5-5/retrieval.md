# Retrieval Diagnosis (20261118-224539-plumbing_01-claude-haiku-5-5)

Source: `log.jsonl`.

## Overall mean recall@k and failure breakdown

| Config | Scored turns | Mean recall@k | Retrieval miss | Wrong reply type | Wrong value | Other |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 40 | 0.618 | 19 | 2 | 2 | 3 |
| C2 | 40 | 0.777 | 9 | 5 | 1 | 1 |

## Mean recall@k by question-type label

| Label | C1 | C2 |
| --- | --- | --- |
| lookup | 0.604 (n=4) | 0.792 (n=4) |
| aggregation | 0.775 (n=10) | 0.925 (n=10) |
| temporal | 0.694 (n=9) | 0.880 (n=9) |
| linking | 0.465 (n=12) | 0.792 (n=12) |
| comparison | 0.682 (n=11) | 0.682 (n=11) |
| dialogue | 0.455 (n=11) | 0.705 (n=11) |
| abstention | 1.000 (n=1) | 1.000 (n=1) |

## Retrieval misses by document type

| Config | Document type | Misses |
| --- | --- | --- |
| C1 | bank row | 6 |
| C1 | invoice | 16 |
| C1 | vendor record | 3 |
| C2 | bank row | 5 |
| C2 | invoice | 3 |
| C2 | vendor record | 2 |

## Retrieval miss details

| Config | Query | Turn | Missed doc | Doc type | Turn text |
| --- | --- | --- | --- | --- | --- |
| C1 | Q01 | 0 | inv_MV-309 | invoice | What bills are due in the next seven days? |
| C1 | Q02 | 0 | inv_PL-314 | invoice | How much do I owe Crestline Pipe & Supply as of September 30? |
| C1 | Q03 | 0 | inv_SUM-44 | invoice | Which invoices are overdue? |
| C1 | Q04 | 0 | txn_0326 | bank row | Did I already pay invoice CP-418? |
| C1 | Q06 | 0 | txn_0322 | bank row | What remains unpaid on MV-309 after the partial payment? |
| C1 | Q07 | 0 | inv_SB-522 | invoice | Which bill should I verify before I pay it? |
| C1 | Q07 | 0 | vh_v_summit | vendor record | Which bill should I verify before I pay it? |
| C1 | Q09 | 0 | inv_CP-418 | invoice | What invoice matches the $788.40 bank payment on September 12? |
| C1 | Q10 | 0 | txn_0304 | bank row | Did I pay any invoice twice? |
| C1 | Q10 | 0 | txn_0308 | bank row | Did I pay any invoice twice? |
| C1 | Q16 | 0 | inv_CP-401 | invoice | List every unpaid Crestline invoice. |
| C1 | Q16 | 0 | inv_CT-88 | invoice | List every unpaid Crestline invoice. |
| C1 | Q16 | 0 | inv_PL-314 | invoice | List every unpaid Crestline invoice. |
| C1 | Q17 | 1 | inv_MV-301 | invoice | What about the one before that? |
| C1 | Q17 | 2 | txn_0304 | bank row | Show me the payment. |
| C1 | Q19 | 1 | inv_CP-401 | invoice | Crestline. |
| C1 | Q19 | 1 | inv_PL-314 | invoice | Crestline. |
| C1 | Q19 | 2 | inv_CP-401 | invoice | Only the overdue part. |
| C1 | Q20 | 1 | vh_v_summit | vendor record | Then draft a verification message. |
| C1 | Q21 | 1 | txn_0326 | bank row | Was the second invoice paid? |
| C1 | Q22 | 1 | inv_SB-510 | invoice | Compared with the previous invoice? |
| C1 | Q22 | 2 | vh_v_summit | vendor record | Could it be a typo? |
| C1 | Q27 | 0 | inv_PL-314 | invoice | Show all invoices from Crestline after it changed its legal name. |
| C1 | Q27 | 0 | inv_CP-445 | invoice | Show all invoices from Crestline after it changed its legal name. |
| C1 | Q28 | 0 | inv_SB-522 | invoice | What is my total outstanding? |
| C2 | Q03 | 0 | inv_SUM-44 | invoice | Which invoices are overdue? |
| C2 | Q04 | 0 | txn_0326 | bank row | Did I already pay invoice CP-418? |
| C2 | Q06 | 0 | txn_0322 | bank row | What remains unpaid on MV-309 after the partial payment? |
| C2 | Q10 | 0 | txn_0304 | bank row | Did I pay any invoice twice? |
| C2 | Q10 | 0 | txn_0308 | bank row | Did I pay any invoice twice? |
| C2 | Q19 | 1 | inv_PL-314 | invoice | Crestline. |
| C2 | Q20 | 1 | vh_v_summit | vendor record | Then draft a verification message. |
| C2 | Q21 | 1 | txn_0326 | bank row | Was the second invoice paid? |
| C2 | Q22 | 1 | inv_SB-510 | invoice | Compared with the previous invoice? |
| C2 | Q22 | 2 | vh_v_summit | vendor record | Could it be a typo? |

## Per-turn recall@k

| Config | Query | Turn | k | Recall@k | Success | Failure category |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | Q01 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q02 | 0 | 8 | 0.75 | False | retrieval miss |
| C1 | Q03 | 0 | 8 | 0.67 | False | retrieval miss |
| C1 | Q04 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q05 | 0 | 8 | 1.00 | True | - |
| C1 | Q06 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q07 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q08 | 0 | 8 | 1.00 | True | - |
| C1 | Q09 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q10 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q11 | 0 | 8 | 1.00 | True | - |
| C1 | Q12 | 0 | 8 | 1.00 | True | - |
| C1 | Q13 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | Q14 | 0 | 8 | 1.00 | True | - |
| C1 | Q15 | 0 | 8 | 1.00 | True | - |
| C1 | Q16 | 0 | 8 | 0.25 | False | retrieval miss |
| C1 | Q17 | 0 | 8 | n/a | False | other |
| C1 | Q17 | 1 | 8 | 0.00 | False | retrieval miss |
| C1 | Q17 | 2 | 8 | 0.00 | False | retrieval miss |
| C1 | Q18 | 0 | 8 | n/a | True | - |
| C1 | Q18 | 1 | 8 | 1.00 | True | - |
| C1 | Q18 | 2 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | Q19 | 0 | 8 | n/a | False | other |
| C1 | Q19 | 1 | 8 | 0.50 | False | retrieval miss |
| C1 | Q19 | 2 | 8 | 0.50 | False | retrieval miss |
| C1 | Q20 | 0 | 8 | n/a | False | other |
| C1 | Q20 | 1 | 8 | 0.00 | False | retrieval miss |
| C1 | Q21 | 1 | 8 | 0.50 | False | retrieval miss |
| C1 | Q21 | 2 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | Q22 | 0 | 8 | n/a | True | - |
| C1 | Q22 | 1 | 8 | 0.50 | False | retrieval miss |
| C1 | Q22 | 2 | 8 | 0.00 | False | retrieval miss |
| C1 | Q23 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | Q24 | 0 | 8 | 1.00 | True | - |
| C1 | Q25 | 0 | 8 | 1.00 | True | - |
| C1 | Q26 | 0 | 8 | 1.00 | True | - |
| C1 | Q27 | 0 | 8 | 0.33 | False | retrieval miss |
| C1 | Q28 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q29 | 0 | 8 | n/a | True | - |
| C1 | Q30 | 0 | 8 | 1.00 | True | - |
| C2 | Q01 | 0 | 8 | 0.50 | True | - |
| C2 | Q02 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | Q03 | 0 | 8 | 0.67 | False | retrieval miss |
| C2 | Q04 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q05 | 0 | 8 | 1.00 | True | - |
| C2 | Q06 | 0 | 8 | 0.50 | False | retrieval miss |
| C2 | Q07 | 0 | 8 | 0.50 | True | - |
| C2 | Q08 | 0 | 8 | 1.00 | True | - |
| C2 | Q09 | 0 | 8 | 1.00 | True | - |
| C2 | Q10 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q11 | 0 | 8 | 1.00 | True | - |
| C2 | Q12 | 0 | 8 | 0.50 | True | - |
| C2 | Q13 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q14 | 0 | 8 | 1.00 | True | - |
| C2 | Q15 | 0 | 8 | 1.00 | True | - |
| C2 | Q16 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q17 | 0 | 8 | n/a | True | - |
| C2 | Q17 | 1 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q17 | 2 | 8 | 1.00 | True | - |
| C2 | Q18 | 0 | 8 | n/a | True | - |
| C2 | Q18 | 1 | 8 | 1.00 | True | - |
| C2 | Q18 | 2 | 8 | 1.00 | True | - |
| C2 | Q19 | 0 | 8 | n/a | True | - |
| C2 | Q19 | 1 | 8 | 0.75 | False | retrieval miss |
| C2 | Q19 | 2 | 8 | 1.00 | True | - |
| C2 | Q20 | 0 | 8 | n/a | False | other |
| C2 | Q20 | 1 | 8 | 0.00 | False | retrieval miss |
| C2 | Q21 | 1 | 8 | 0.50 | False | retrieval miss |
| C2 | Q21 | 2 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q22 | 0 | 8 | n/a | True | - |
| C2 | Q22 | 1 | 8 | 0.50 | False | retrieval miss |
| C2 | Q22 | 2 | 8 | 0.00 | False | retrieval miss |
| C2 | Q23 | 0 | 8 | 1.00 | True | - |
| C2 | Q24 | 0 | 8 | 1.00 | True | - |
| C2 | Q25 | 0 | 8 | 1.00 | True | - |
| C2 | Q26 | 0 | 8 | 1.00 | True | - |
| C2 | Q27 | 0 | 8 | 1.00 | True | - |
| C2 | Q28 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q29 | 0 | 8 | n/a | True | - |
| C2 | Q30 | 0 | 8 | 1.00 | True | - |

## Document-level retrieval at rank (QA lecture)

| Config | Turns | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 34 | 0.294 | 0.186 | 0.147 | 0.140 | 0.250 | 0.375 | 0.473 | 0.618 | 0.435 |
| C2 | 34 | 0.176 | 0.225 | 0.212 | 0.184 | 0.147 | 0.424 | 0.574 | 0.777 | 0.417 |
