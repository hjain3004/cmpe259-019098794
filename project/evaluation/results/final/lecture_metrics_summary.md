# Course-Lecture Evaluation Metrics Summary

Offline evaluation on `answer_system_v2` (commit `7a5dd10`). Held-out (`landscaping_01`) and development splits are never pooled.

---

## 1. Reply-Type Classification (POS / NER lecture: accuracy vs most-frequent-class baseline)

### Held-out (landscaping_01) (Majority baseline: `ANSWER` = 28/40 = 70.0%)

| Config | Accuracy | vs Majority | Macro-F1 | ANSWER F1 | CLARIFY F1 | ABSTAIN F1 | WARN F1 | Unparsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 77.5% | +7.5% | 0.772 | 0.833 | 0.615 | 0.750 | 0.889 | 2 |
| C1 | 67.5% | -2.5% | 0.586 | 0.809 | 0.500 | 0.308 | 0.727 | 1 |
| C2 | 65.0% | -5.0% | 0.587 | 0.756 | 0.545 | 0.500 | 0.545 | 1 |
| C3 | 85.0% | +15.0% | 0.829 | 0.902 | 0.667 | 0.857 | 0.889 | 1 |
| C4 | 82.5% | +12.5% | 0.810 | 0.880 | 0.615 | 0.857 | 0.889 | 1 |

### Development (cafe_01 + plumbing_01) (Majority baseline: `ANSWER` = 46/68 = 67.6%)

| Config | Accuracy | vs Majority | Macro-F1 | ANSWER F1 | CLARIFY F1 | ABSTAIN F1 | WARN F1 | Unparsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 79.4% | +11.8% | 0.770 | 0.857 | 0.588 | 0.909 | 0.727 | 2 |
| C1 | 60.3% | -7.4% | 0.554 | 0.722 | 0.444 | 0.385 | 0.667 | 2 |
| C2 | 69.1% | +1.5% | 0.633 | 0.779 | 0.526 | 0.526 | 0.700 | 1 |
| C3 | 82.4% | +14.7% | 0.825 | 0.881 | 0.545 | 1.000 | 0.875 | 2 |
| C4 | 85.3% | +17.6% | 0.851 | 0.907 | 0.556 | 1.000 | 0.941 | 3 |

### Expanded development (bakery_01 + clinic_01) (Majority baseline: `ANSWER` = 36/53 = 67.9%)

| Config | Accuracy | vs Majority | Macro-F1 | ANSWER F1 | CLARIFY F1 | ABSTAIN F1 | WARN F1 | Unparsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 84.9% | +17.0% | 0.775 | 0.914 | 0.727 | 0.857 | 0.600 | 1 |
| C1 | 83.0% | +15.1% | 0.738 | 0.912 | 0.667 | 0.706 | 0.667 | 0 |
| C2 | 81.1% | +13.2% | 0.707 | 0.909 | 0.667 | 0.706 | 0.545 | 0 |
| C3 | 73.6% | +5.7% | 0.635 | 0.853 | 0.600 | 0.421 | 0.667 | 0 |
| C4 | 77.4% | +9.4% | 0.699 | 0.857 | 0.800 | 0.471 | 0.667 | 0 |

---

## 2. Document-Level Retrieval at Rank for C1 and C2 (QA lecture: precision at rank, recall by rank, MRR)

| Split | Config | Turns w/ gold | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Held-out (landscaping_01) | C1 | 34 | 0.206 | 0.176 | 0.129 | 0.132 | 0.176 | 0.368 | 0.407 | 0.571 | 0.364 |
| Held-out (landscaping_01) | C2 | 34 | 0.265 | 0.255 | 0.200 | 0.158 | 0.213 | 0.414 | 0.547 | 0.652 | 0.441 |
| Development (cafe_01 + plumbing_01) | C1 | 56 | 0.268 | 0.185 | 0.146 | 0.136 | 0.205 | 0.362 | 0.466 | 0.625 | 0.420 |
| Development (cafe_01 + plumbing_01) | C2 | 56 | 0.143 | 0.190 | 0.204 | 0.167 | 0.116 | 0.365 | 0.589 | 0.757 | 0.376 |
| Expanded development (bakery_01 + clinic_01) | C1 | 43 | 0.535 | 0.403 | 0.335 | 0.233 | 0.337 | 0.609 | 0.804 | 0.897 | 0.687 |
| Expanded development (bakery_01 + clinic_01) | C2 | 43 | 0.442 | 0.380 | 0.316 | 0.241 | 0.279 | 0.560 | 0.729 | 0.919 | 0.630 |

---

## 3. NER-Style Extraction Precision, Recall, and F1 (NER lecture: unit exact match, partial = 1 FP + 1 FN)

| Split / Dataset | Docs | Overall Micro-P | Overall Micro-R | Overall Micro-F1 | Total F1 | Line-Items F1 | Subtotals/Tax note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Held-out (`landscaping_01`) | 13 | 1.000 | 0.948 | 0.974 | 1.000 | 1.000 | subtotal+tax FN=8 |
| Development (`cafe_01 + plumbing_01`) | 21 | 1.000 | 0.953 | 0.976 | 1.000 | 1.000 | subtotal+tax FN=12 |
| Real receipts (`SROIE`: company/date/total) | 626 | 0.952 | 0.947 | 0.949 | 0.973 | — | company=0.879, date=0.996 |

---

## 4. Citation F1 (mean per-turn F1 and corpus micro-F1)

| Split | Config | Mean recall | Mean precision | Mean F1 | Micro-F1 |
| --- | --- | --- | --- | --- | --- |
| Held-out (landscaping_01) | C0 | 1.000 | 0.541 | 0.660 | 0.570 |
| Held-out (landscaping_01) | C1 | 0.571 | 0.366 | 0.429 | 0.400 |
| Held-out (landscaping_01) | C2 | 0.672 | 0.473 | 0.536 | 0.491 |
| Held-out (landscaping_01) | C3 | 0.838 | 0.611 | 0.683 | 0.724 |
| Held-out (landscaping_01) | C4 | 0.747 | 0.552 | 0.617 | 0.685 |
| Development (cafe_01 + plumbing_01) | C0 | 0.977 | 0.471 | 0.609 | 0.566 |
| Development (cafe_01 + plumbing_01) | C1 | 0.598 | 0.330 | 0.406 | 0.397 |
| Development (cafe_01 + plumbing_01) | C2 | 0.744 | 0.428 | 0.517 | 0.497 |
| Development (cafe_01 + plumbing_01) | C3 | 0.799 | 0.653 | 0.698 | 0.721 |
| Development (cafe_01 + plumbing_01) | C4 | 0.846 | 0.657 | 0.718 | 0.739 |
| Expanded development (bakery_01 + clinic_01) | C0 | 0.992 | 0.588 | 0.708 | 0.710 |
| Expanded development (bakery_01 + clinic_01) | C1 | 0.864 | 0.551 | 0.642 | 0.625 |
| Expanded development (bakery_01 + clinic_01) | C2 | 0.901 | 0.600 | 0.694 | 0.675 |
| Expanded development (bakery_01 + clinic_01) | C3 | 0.777 | 0.712 | 0.709 | 0.751 |
| Expanded development (bakery_01 + clinic_01) | C4 | 0.785 | 0.723 | 0.721 | 0.758 |

---

## 5. Significance Testing & Attention-Item Evaluation (NER lecture: paired exact McNemar & `(scenario, query_id)` bootstrap)

| Split | Pair (A vs B) | Discordant (A:B) | Exact McNemar p | Diff (A - B) | 95% Bootstrap CI |
| --- | --- | --- | --- | --- | --- |
| Held-out (landscaping_01) | C0 vs C1 | 10:1 | 0.012 | +22.5% | [+7.9%, +36.6%] |
| Held-out (landscaping_01) | C0 vs C2 | 7:2 | 0.180 | +12.5% | [-2.6%, +28.2%] |
| Held-out (landscaping_01) | C0 vs C3 | 2:6 | 0.289 | -10.0% | [-25.0%, +2.6%] |
| Held-out (landscaping_01) | C0 vs C4 | 4:6 | 0.754 | -5.0% | [-22.0%, +10.0%] |
| Held-out (landscaping_01) | C1 vs C2 | 3:7 | 0.344 | -10.0% | [-25.0%, +7.3%] |
| Held-out (landscaping_01) | C1 vs C3 | 0:13 | 0.000 | -32.5% | [-47.4%, -18.7%] |
| Held-out (landscaping_01) | C1 vs C4 | 2:13 | 0.007 | -27.5% | [-44.1%, -11.6%] |
| Held-out (landscaping_01) | C2 vs C3 | 0:9 | 0.004 | -22.5% | [-37.8%, -9.5%] |
| Held-out (landscaping_01) | C2 vs C4 | 3:10 | 0.092 | -17.5% | [-36.4%, +0.0%] |
| Held-out (landscaping_01) | C3 vs C4 | 3:1 | 0.625 | +5.0% | [-4.9%, +15.0%] |
| Development (cafe_01 + plumbing_01) | C0 vs C1 | 21:3 | 0.000 | +26.5% | [+12.7%, +40.6%] |
| Development (cafe_01 + plumbing_01) | C0 vs C2 | 13:6 | 0.167 | +10.3% | [-2.9%, +23.3%] |
| Development (cafe_01 + plumbing_01) | C0 vs C3 | 4:11 | 0.118 | -10.3% | [-22.0%, +0.0%] |
| Development (cafe_01 + plumbing_01) | C0 vs C4 | 4:13 | 0.049 | -13.2% | [-25.4%, -1.6%] |
| Development (cafe_01 + plumbing_01) | C1 vs C2 | 2:13 | 0.007 | -16.2% | [-27.6%, -4.8%] |
| Development (cafe_01 + plumbing_01) | C1 vs C3 | 5:30 | 0.000 | -36.8% | [-52.9%, -20.3%] |
| Development (cafe_01 + plumbing_01) | C1 vs C4 | 4:31 | 0.000 | -39.7% | [-55.1%, -24.6%] |
| Development (cafe_01 + plumbing_01) | C2 vs C3 | 5:19 | 0.007 | -20.6% | [-35.1%, -6.8%] |
| Development (cafe_01 + plumbing_01) | C2 vs C4 | 5:21 | 0.002 | -23.5% | [-37.9%, -9.8%] |
| Development (cafe_01 + plumbing_01) | C3 vs C4 | 2:4 | 0.688 | -2.9% | [-10.0%, +4.2%] |
| Expanded development (bakery_01 + clinic_01) | C0 vs C1 | 12:4 | 0.077 | +15.1% | [+0.0%, +32.0%] |
| Expanded development (bakery_01 + clinic_01) | C0 vs C2 | 13:3 | 0.021 | +18.9% | [+3.9%, +35.4%] |
| Expanded development (bakery_01 + clinic_01) | C0 vs C3 | 13:6 | 0.167 | +13.2% | [-1.9%, +28.3%] |
| Expanded development (bakery_01 + clinic_01) | C0 vs C4 | 12:6 | 0.238 | +11.3% | [-2.1%, +25.4%] |
| Expanded development (bakery_01 + clinic_01) | C1 vs C2 | 7:5 | 0.774 | +3.8% | [-9.6%, +16.4%] |
| Expanded development (bakery_01 + clinic_01) | C1 vs C3 | 12:13 | 1.000 | -1.9% | [-20.4%, +15.7%] |
| Expanded development (bakery_01 + clinic_01) | C1 vs C4 | 12:14 | 0.845 | -3.8% | [-24.0%, +14.5%] |
| Expanded development (bakery_01 + clinic_01) | C2 vs C3 | 12:15 | 0.701 | -5.7% | [-23.9%, +12.2%] |
| Expanded development (bakery_01 + clinic_01) | C2 vs C4 | 12:16 | 0.572 | -7.5% | [-26.9%, +10.3%] |
| Expanded development (bakery_01 + clinic_01) | C3 vs C4 | 2:3 | 1.000 | -1.9% | [-10.4%, +6.0%] |

### Attention-item detection (C3 extracted vs C4 gold)

| Split | Bundle | Store | Expected | Found | TP | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Held-out | landscaping_01 | C3 | 15 | 19 | 12 | 63.2% | 80.0% |
| Held-out | landscaping_01 | C4 | 15 | 19 | 12 | 63.2% | 80.0% |
| Development | cafe_01 | C3 | 13 | 13 | 11 | 84.6% | 84.6% |
| Development | cafe_01 | C4 | 13 | 13 | 11 | 84.6% | 84.6% |
| Development | plumbing_01 | C3 | 15 | 15 | 13 | 86.7% | 86.7% |
| Development | plumbing_01 | C4 | 15 | 15 | 13 | 86.7% | 86.7% |
