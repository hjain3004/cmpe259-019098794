# Attention-Item Evaluation

## Development bundles

| Bundle | Store | Expected | Found | TP | Missed | Spurious | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cafe_01 | C3 | 13 | 13 | 11 | 2 | 2 | 84.6% | 84.6% |
| cafe_01 | C4 | 13 | 13 | 11 | 2 | 2 | 84.6% | 84.6% |
| plumbing_01 | C3 | 15 | 15 | 13 | 2 | 2 | 86.7% | 86.7% |
| plumbing_01 | C4 | 15 | 15 | 13 | 2 | 2 | 86.7% | 86.7% |

### cafe_01 (C3) by item type

| Item type | Expected | Found | Missed | Spurious | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| overdue_bill | 2 | 2 | — | — | 100% | 100% |
| duplicate_payment | 1 | 0 | NS-1031 | — | n/a | 0% |
| partial_payment | 1 | 0 | GP-228 | — | n/a | 0% |
| candidate_payment_link | 0 | 2 | — | GP-228:txn_0181, NS-1031:txn_0109 | 0% | n/a |
| unmatched_bank_debit | 7 | 7 | — | — | 100% | 100% |
| bank_detail_mismatch | 1 | 1 | — | — | 100% | 100% |
| message_conflict | 1 | 1 | — | — | 100% | 100% |

### cafe_01 (C4) by item type

| Item type | Expected | Found | Missed | Spurious | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| overdue_bill | 2 | 2 | — | — | 100% | 100% |
| duplicate_payment | 1 | 0 | NS-1031 | — | n/a | 0% |
| partial_payment | 1 | 0 | GP-228 | — | n/a | 0% |
| candidate_payment_link | 0 | 2 | — | GP-228:txn_0181, NS-1031:txn_0109 | 0% | n/a |
| unmatched_bank_debit | 7 | 7 | — | — | 100% | 100% |
| bank_detail_mismatch | 1 | 1 | — | — | 100% | 100% |
| message_conflict | 1 | 1 | — | — | 100% | 100% |

### plumbing_01 (C3) by item type

| Item type | Expected | Found | Missed | Spurious | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| overdue_bill | 3 | 3 | — | — | 100% | 100% |
| duplicate_bill | 1 | 1 | — | — | 100% | 100% |
| duplicate_payment | 1 | 0 | MV-301 | — | n/a | 0% |
| partial_payment | 2 | 1 | MV-309 | — | 100% | 50% |
| candidate_payment_link | 0 | 2 | — | MV-301:txn_0308, MV-309:txn_0322 | 0% | n/a |
| unmatched_bank_debit | 4 | 4 | — | — | 100% | 100% |
| bank_detail_mismatch | 1 | 1 | — | — | 100% | 100% |
| total_mismatch | 1 | 1 | — | — | 100% | 100% |
| due_date_conflict | 1 | 1 | — | — | 100% | 100% |
| message_conflict | 1 | 1 | — | — | 100% | 100% |

### plumbing_01 (C4) by item type

| Item type | Expected | Found | Missed | Spurious | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| overdue_bill | 3 | 3 | — | — | 100% | 100% |
| duplicate_bill | 1 | 1 | — | — | 100% | 100% |
| duplicate_payment | 1 | 0 | MV-301 | — | n/a | 0% |
| partial_payment | 2 | 1 | MV-309 | — | 100% | 50% |
| candidate_payment_link | 0 | 2 | — | MV-301:txn_0308, MV-309:txn_0322 | 0% | n/a |
| unmatched_bank_debit | 4 | 4 | — | — | 100% | 100% |
| bank_detail_mismatch | 1 | 1 | — | — | 100% | 100% |
| total_mismatch | 1 | 1 | — | — | 100% | 100% |
| due_date_conflict | 1 | 1 | — | — | 100% | 100% |
| message_conflict | 1 | 1 | — | — | 100% | 100% |

## Held-out bundle

| Bundle | Store | Expected | Found | TP | Missed | Spurious | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| landscaping_01 | C3 | 15 | 19 | 12 | 3 | 7 | 63.2% | 80.0% |
| landscaping_01 | C4 | 15 | 19 | 12 | 3 | 7 | 63.2% | 80.0% |

### landscaping_01 (C3) by item type

| Item type | Expected | Found | Missed | Spurious | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| overdue_bill | 3 | 3 | — | — | 100% | 100% |
| duplicate_bill | 1 | 1 | — | — | 100% | 100% |
| duplicate_payment | 1 | 0 | RL-204 | — | n/a | 0% |
| partial_payment | 2 | 0 | PL-314, RL-215 | — | n/a | 0% |
| candidate_payment_link | 0 | 7 | — | CT-88:txn_0516, ML-090:txn_0512, ML-90:txn_0512, MN-480:txn_0516, PL-314:txn_0516, RL-204:txn_0506, RL-215:txn_0512 | 0% | n/a |
| unmatched_bank_debit | 4 | 4 | — | — | 100% | 100% |
| bank_detail_mismatch | 1 | 1 | — | — | 100% | 100% |
| total_mismatch | 1 | 1 | — | — | 100% | 100% |
| due_date_conflict | 1 | 1 | — | — | 100% | 100% |
| message_conflict | 1 | 1 | — | — | 100% | 100% |

### landscaping_01 (C4) by item type

| Item type | Expected | Found | Missed | Spurious | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| overdue_bill | 3 | 3 | — | — | 100% | 100% |
| duplicate_bill | 1 | 1 | — | — | 100% | 100% |
| duplicate_payment | 1 | 0 | RL-204 | — | n/a | 0% |
| partial_payment | 2 | 0 | PL-314, RL-215 | — | n/a | 0% |
| candidate_payment_link | 0 | 7 | — | CT-88:txn_0516, ML-090:txn_0512, ML-90:txn_0512, MN-480:txn_0516, PL-314:txn_0516, RL-204:txn_0506, RL-215:txn_0512 | 0% | n/a |
| unmatched_bank_debit | 4 | 4 | — | — | 100% | 100% |
| bank_detail_mismatch | 1 | 1 | — | — | 100% | 100% |
| total_mismatch | 1 | 1 | — | — | 100% | 100% |
| due_date_conflict | 1 | 1 | — | — | 100% | 100% |
| message_conflict | 1 | 1 | — | — | 100% | 100% |

