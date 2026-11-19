# Retrieval Diagnosis (20261117-234352-cafe_01-claude-haiku-5-5)

Source: `rescored/log.jsonl`.

## Overall mean recall@k and failure breakdown

| Config | Scored turns | Mean recall@k | Retrieval miss | Wrong reply type | Wrong value | Other |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 28 | 0.636 | 9 | 6 | 0 | 1 |
| C2 | 28 | 0.727 | 5 | 4 | 1 | 3 |

## Mean recall@k by question-type label

| Label | C1 | C2 |
| --- | --- | --- |
| lookup | 0.750 (n=4) | 0.625 (n=4) |
| aggregation | 0.583 (n=6) | 0.917 (n=6) |
| temporal | 0.500 (n=5) | 0.800 (n=5) |
| linking | 0.611 (n=9) | 0.667 (n=9) |
| comparison | 0.667 (n=6) | 0.667 (n=6) |
| dialogue | 0.583 (n=6) | 0.833 (n=6) |
| abstention | 1.000 (n=1) | 1.000 (n=1) |

## Retrieval misses by document type

| Config | Document type | Misses |
| --- | --- | --- |
| C1 | bank row | 4 |
| C1 | invoice | 5 |
| C1 | vendor record | 1 |
| C2 | bank row | 4 |
| C2 | invoice | 1 |
| C2 | vendor record | 1 |

## Retrieval miss details

| Config | Query | Turn | Missed doc | Doc type | Turn text |
| --- | --- | --- | --- | --- | --- |
| C1 | Q01 | 0 | inv_NS-1062 | invoice | What bills are due in the next seven days? |
| C1 | Q04 | 0 | txn_0193 | bank row | Did I already pay invoice NS-1048? |
| C1 | Q06 | 0 | txn_0181 | bank row | What remains unpaid on GP-228 after the partial payment? |
| C1 | Q10 | 0 | txn_0102 | bank row | Did I pay any invoice twice? |
| C1 | Q10 | 0 | txn_0109 | bank row | Did I pay any invoice twice? |
| C1 | Q13 | 0 | inv_BW-760 | invoice | Is the amount on BW-771 unusual for this vendor? |
| C1 | Q14 | 0 | inv_BW-760 | invoice | How much did I spend on coffee beans in August? |
| C1 | Q17 | 1 | inv_GP-221 | invoice | What about the one before that? |
| C1 | Q19 | 1 | inv_NS-1062 | invoice | Northside. |
| C1 | Q20 | 1 | vh_v_beanworks | vendor record | Then draft a verification message. |
| C2 | Q01 | 0 | inv_NS-1062 | invoice | What bills are due in the next seven days? |
| C2 | Q04 | 0 | txn_0193 | bank row | Did I already pay invoice NS-1048? |
| C2 | Q06 | 0 | txn_0181 | bank row | What remains unpaid on GP-228 after the partial payment? |
| C2 | Q10 | 0 | txn_0102 | bank row | Did I pay any invoice twice? |
| C2 | Q10 | 0 | txn_0109 | bank row | Did I pay any invoice twice? |
| C2 | Q20 | 1 | vh_v_beanworks | vendor record | Then draft a verification message. |

## Per-turn recall@k

| Config | Query | Turn | k | Recall@k | Success | Failure category |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | Q01 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q02 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | Q03 | 0 | 8 | 1.00 | False | other |
| C1 | Q04 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q06 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q07 | 0 | 8 | 0.50 | True | - |
| C1 | Q08 | 0 | 8 | 1.00 | True | - |
| C1 | Q09 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | Q10 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q11 | 0 | 8 | 1.00 | True | - |
| C1 | Q12 | 0 | 8 | 1.00 | True | - |
| C1 | Q13 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | Q14 | 0 | 8 | 0.00 | False | retrieval miss |
| C1 | Q15 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | Q16 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | Q17 | 0 | 8 | n/a | True | - |
| C1 | Q17 | 1 | 8 | 0.00 | False | retrieval miss |
| C1 | Q17 | 2 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | Q18 | 0 | 8 | n/a | True | - |
| C1 | Q18 | 1 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | Q18 | 2 | 8 | 1.00 | True | - |
| C1 | Q19 | 0 | 8 | n/a | True | - |
| C1 | Q19 | 1 | 8 | 0.50 | False | retrieval miss |
| C1 | Q19 | 2 | 8 | n/a | True | - |
| C1 | Q20 | 0 | 8 | n/a | True | - |
| C1 | Q20 | 1 | 8 | 0.00 | False | retrieval miss |
| C1 | Q29 | 0 | 8 | n/a | True | - |
| C1 | Q30 | 0 | 8 | 1.00 | True | - |
| C2 | Q01 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q02 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q03 | 0 | 8 | 1.00 | False | other |
| C2 | Q04 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q06 | 0 | 8 | 0.50 | False | retrieval miss |
| C2 | Q07 | 0 | 8 | 0.50 | True | - |
| C2 | Q08 | 0 | 8 | 1.00 | True | - |
| C2 | Q09 | 0 | 8 | 1.00 | True | - |
| C2 | Q10 | 0 | 8 | 0.00 | False | retrieval miss |
| C2 | Q11 | 0 | 8 | 1.00 | True | - |
| C2 | Q12 | 0 | 8 | 0.50 | True | - |
| C2 | Q13 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q14 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q15 | 0 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | Q16 | 0 | 8 | 0.50 | True | - |
| C2 | Q17 | 0 | 8 | n/a | False | other |
| C2 | Q17 | 1 | 8 | 1.00 | True | - |
| C2 | Q17 | 2 | 8 | 1.00 | True | - |
| C2 | Q18 | 0 | 8 | n/a | False | other |
| C2 | Q18 | 1 | 8 | 1.00 | True | - |
| C2 | Q18 | 2 | 8 | 1.00 | True | - |
| C2 | Q19 | 0 | 8 | n/a | True | - |
| C2 | Q19 | 1 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | Q19 | 2 | 8 | n/a | True | - |
| C2 | Q20 | 0 | 8 | n/a | True | - |
| C2 | Q20 | 1 | 8 | 0.00 | False | retrieval miss |
| C2 | Q29 | 0 | 8 | n/a | True | - |
| C2 | Q30 | 0 | 8 | 1.00 | True | - |
