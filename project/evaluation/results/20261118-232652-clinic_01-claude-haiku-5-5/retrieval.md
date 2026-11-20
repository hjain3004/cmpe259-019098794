# Retrieval Diagnosis (20261118-232652-clinic_01-claude-haiku-5-5)

Source: `log.jsonl`.

## Overall mean recall@k and failure breakdown

| Config | Scored turns | Mean recall@k | Retrieval miss | Wrong reply type | Wrong value | Other |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 26 | 0.928 | 3 | 1 | 6 | 2 |
| C2 | 26 | 0.924 | 4 | 2 | 7 | 1 |

## Mean recall@k by question-type label

| Label | C1 | C2 |
| --- | --- | --- |
| lookup | 0.889 (n=3) | 0.889 (n=3) |
| aggregation | 1.000 (n=10) | 1.000 (n=10) |
| temporal | 0.933 (n=5) | 0.867 (n=5) |
| linking | 0.946 (n=14) | 0.940 (n=14) |
| comparison | 0.900 (n=5) | 0.900 (n=5) |
| dialogue | 1.000 (n=11) | 0.970 (n=11) |
| abstention | 0.625 (n=2) | 0.750 (n=2) |

## Retrieval misses by document type

| Config | Document type | Misses |
| --- | --- | --- |
| C1 | invoice | 4 |
| C1 | vendor record | 1 |
| C2 | credit note | 1 |
| C2 | invoice | 3 |
| C2 | vendor record | 1 |

## Retrieval miss details

| Config | Query | Turn | Missed doc | Doc type | Turn text |
| --- | --- | --- | --- | --- | --- |
| C1 | D201 | 0 | inv_INV-902--biopet | invoice | What bills are due in the next seven days? |
| C1 | D205 | 0 | inv_MV-112 | invoice | Which MedVet invoices did the $1,200.00 payment on September 16 pay? |
| C1 | D205 | 0 | inv_MV-119 | invoice | Which MedVet invoices did the $1,200.00 payment on September 16 pay? |
| C1 | D205 | 0 | inv_MV-121 | invoice | Which MedVet invoices did the $1,200.00 payment on September 16 pay? |
| C1 | D211 | 0 | vh_v_biopet | vendor record | Should I pay BioPet invoice BP-310 to the Apex Digital Bank account? |
| C2 | D201 | 0 | inv_AV-79 | invoice | What bills are due in the next seven days? |
| C2 | D205 | 0 | inv_MV-112 | invoice | Which MedVet invoices did the $1,200.00 payment on September 16 pay? |
| C2 | D205 | 0 | inv_MV-121 | invoice | Which MedVet invoices did the $1,200.00 payment on September 16 pay? |
| C2 | D211 | 0 | vh_v_biopet | vendor record | Should I pay BioPet invoice BP-310 to the Apex Digital Bank account? |
| C2 | D216 | 1 | cn_CN-415 | credit note | Which of their bills is overdue? |

## Per-turn recall@k

| Config | Query | Turn | k | Recall@k | Success | Failure category |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | D201 | 0 | 8 | 0.67 | False | retrieval miss |
| C1 | D202 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | D203 | 0 | 8 | 1.00 | True | - |
| C1 | D204 | 0 | 8 | 1.00 | True | - |
| C1 | D205 | 0 | 8 | 0.25 | False | retrieval miss |
| C1 | D206 | 0 | 8 | n/a | True | - |
| C1 | D207 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | D208 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | D209 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | D210 | 0 | 8 | 1.00 | True | - |
| C1 | D211 | 0 | 8 | 0.50 | False | retrieval miss |
| C1 | D212 | 0 | 8 | 1.00 | True | - |
| C1 | D213 | 0 | 8 | n/a | True | - |
| C1 | D213 | 1 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | D213 | 2 | 8 | 1.00 | True | - |
| C1 | D214 | 0 | 8 | 1.00 | True | - |
| C1 | D214 | 1 | 8 | 1.00 | True | - |
| C1 | D214 | 2 | 8 | 1.00 | True | - |
| C1 | D215 | 1 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C1 | D215 | 2 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C1 | D216 | 0 | 8 | 1.00 | True | - |
| C1 | D216 | 1 | 8 | 1.00 | True | - |
| C1 | D217 | 0 | 8 | 1.00 | True | - |
| C1 | D217 | 1 | 8 | n/a | True | - |
| C1 | D218 | 0 | 8 | n/a | False | other |
| C1 | D218 | 1 | 8 | 1.00 | False | other |
| C2 | D201 | 0 | 8 | 0.67 | False | retrieval miss |
| C2 | D202 | 0 | 8 | 1.00 | True | - |
| C2 | D203 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D204 | 0 | 8 | 1.00 | True | - |
| C2 | D205 | 0 | 8 | 0.50 | False | retrieval miss |
| C2 | D206 | 0 | 8 | n/a | True | - |
| C2 | D207 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D208 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D209 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D210 | 0 | 8 | 1.00 | True | - |
| C2 | D211 | 0 | 8 | 0.50 | False | retrieval miss |
| C2 | D212 | 0 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D213 | 0 | 8 | n/a | True | - |
| C2 | D213 | 1 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D213 | 2 | 8 | 1.00 | True | - |
| C2 | D214 | 0 | 8 | 1.00 | True | - |
| C2 | D214 | 1 | 8 | 1.00 | True | - |
| C2 | D214 | 2 | 8 | 1.00 | True | - |
| C2 | D215 | 1 | 8 | 1.00 | False | evidence retrieved, wrong value |
| C2 | D215 | 2 | 8 | 1.00 | False | evidence retrieved, wrong reply type |
| C2 | D216 | 0 | 8 | 1.00 | True | - |
| C2 | D216 | 1 | 8 | 0.67 | False | retrieval miss |
| C2 | D217 | 0 | 8 | 1.00 | True | - |
| C2 | D217 | 1 | 8 | n/a | True | - |
| C2 | D218 | 0 | 8 | n/a | False | other |
| C2 | D218 | 1 | 8 | 1.00 | False | evidence retrieved, wrong reply type |

## Document-level retrieval at rank (QA lecture)

| Config | Turns | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 22 | 0.545 | 0.424 | 0.327 | 0.244 | 0.345 | 0.633 | 0.769 | 0.928 | 0.691 |
| C2 | 22 | 0.455 | 0.394 | 0.309 | 0.244 | 0.299 | 0.602 | 0.723 | 0.924 | 0.651 |
