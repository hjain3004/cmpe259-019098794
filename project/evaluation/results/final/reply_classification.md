# Reply-Type Classification (POS / NER Lecture)

Compares predicted `answerability` across `{ANSWER, CLARIFY, ABSTAIN, WARN}` (plus `UNPARSED`) against a majority-class baseline that always predicts the most frequent expected label in that split.

## Held-out (landscaping_01)

Majority-class baseline: `ANSWER` (28/40 = 70.0%).

| Config | Turns | Accuracy | Majority baseline | vs Majority | Macro-F1 | ANSWER F1 | CLARIFY F1 | ABSTAIN F1 | WARN F1 | Unparsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 40 | 77.5% | 70.0% | +7.5% | 0.772 | 0.833 | 0.615 | 0.750 | 0.889 | 2 |
| C1 | 40 | 67.5% | 70.0% | -2.5% | 0.586 | 0.809 | 0.500 | 0.308 | 0.727 | 1 |
| C2 | 40 | 65.0% | 70.0% | -5.0% | 0.587 | 0.756 | 0.545 | 0.500 | 0.545 | 1 |
| C3 | 40 | 85.0% | 70.0% | +15.0% | 0.829 | 0.902 | 0.667 | 0.857 | 0.889 | 1 |
| C4 | 40 | 82.5% | 70.0% | +12.5% | 0.810 | 0.880 | 0.615 | 0.857 | 0.889 | 1 |

### Held-out (landscaping_01) — C0 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 20 | 4 | 2 | 0 | 2 | 28 | 1.000 | 0.714 | 0.833 |
| CLARIFY | 0 | 4 | 0 | 0 | 0 | 4 | 0.444 | 1.000 | 0.615 |
| ABSTAIN | 0 | 0 | 3 | 0 | 0 | 3 | 0.600 | 1.000 | 0.750 |
| WARN | 0 | 1 | 0 | 4 | 0 | 5 | 1.000 | 0.800 | 0.889 |

### Held-out (landscaping_01) — C1 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 19 | 1 | 7 | 1 | 0 | 28 | 1.000 | 0.679 | 0.809 |
| CLARIFY | 0 | 2 | 1 | 0 | 1 | 4 | 0.500 | 0.500 | 0.500 |
| ABSTAIN | 0 | 0 | 2 | 1 | 0 | 3 | 0.200 | 0.667 | 0.308 |
| WARN | 0 | 1 | 0 | 4 | 0 | 5 | 0.667 | 0.800 | 0.727 |

### Held-out (landscaping_01) — C2 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 17 | 2 | 6 | 2 | 1 | 28 | 1.000 | 0.607 | 0.756 |
| CLARIFY | 0 | 3 | 0 | 1 | 0 | 4 | 0.429 | 0.750 | 0.545 |
| ABSTAIN | 0 | 0 | 3 | 0 | 0 | 3 | 0.333 | 1.000 | 0.500 |
| WARN | 0 | 2 | 0 | 3 | 0 | 5 | 0.500 | 0.600 | 0.545 |

### Held-out (landscaping_01) — C3 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 23 | 3 | 1 | 0 | 1 | 28 | 1.000 | 0.821 | 0.902 |
| CLARIFY | 0 | 4 | 0 | 0 | 0 | 4 | 0.500 | 1.000 | 0.667 |
| ABSTAIN | 0 | 0 | 3 | 0 | 0 | 3 | 0.750 | 1.000 | 0.857 |
| WARN | 0 | 1 | 0 | 4 | 0 | 5 | 1.000 | 0.800 | 0.889 |

### Held-out (landscaping_01) — C4 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 22 | 4 | 1 | 0 | 1 | 28 | 1.000 | 0.786 | 0.880 |
| CLARIFY | 0 | 4 | 0 | 0 | 0 | 4 | 0.444 | 1.000 | 0.615 |
| ABSTAIN | 0 | 0 | 3 | 0 | 0 | 3 | 0.750 | 1.000 | 0.857 |
| WARN | 0 | 1 | 0 | 4 | 0 | 5 | 1.000 | 0.800 | 0.889 |

## Development (cafe_01 + plumbing_01)

Majority-class baseline: `ANSWER` (46/68 = 67.6%).

| Config | Turns | Accuracy | Majority baseline | vs Majority | Macro-F1 | ANSWER F1 | CLARIFY F1 | ABSTAIN F1 | WARN F1 | Unparsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 68 | 79.4% | 67.6% | +11.8% | 0.770 | 0.857 | 0.588 | 0.909 | 0.727 | 2 |
| C1 | 68 | 60.3% | 67.6% | -7.4% | 0.554 | 0.722 | 0.444 | 0.385 | 0.667 | 2 |
| C2 | 68 | 69.1% | 67.6% | +1.5% | 0.633 | 0.779 | 0.526 | 0.526 | 0.700 | 1 |
| C3 | 68 | 82.4% | 67.6% | +14.7% | 0.825 | 0.881 | 0.545 | 1.000 | 0.875 | 2 |
| C4 | 68 | 85.3% | 67.6% | +17.6% | 0.851 | 0.907 | 0.556 | 1.000 | 0.941 | 3 |

### Development (cafe_01 + plumbing_01) — C0 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 36 | 3 | 0 | 5 | 2 | 46 | 0.947 | 0.783 | 0.857 |
| CLARIFY | 2 | 5 | 0 | 0 | 0 | 7 | 0.500 | 0.714 | 0.588 |
| ABSTAIN | 0 | 1 | 5 | 0 | 0 | 6 | 1.000 | 0.833 | 0.909 |
| WARN | 0 | 1 | 0 | 8 | 0 | 9 | 0.615 | 0.889 | 0.727 |

### Development (cafe_01 + plumbing_01) — C1 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 26 | 3 | 14 | 3 | 0 | 46 | 1.000 | 0.565 | 0.722 |
| CLARIFY | 0 | 4 | 1 | 0 | 2 | 7 | 0.364 | 0.571 | 0.444 |
| ABSTAIN | 0 | 1 | 5 | 0 | 0 | 6 | 0.250 | 0.833 | 0.385 |
| WARN | 0 | 3 | 0 | 6 | 0 | 9 | 0.667 | 0.667 | 0.667 |

### Development (cafe_01 + plumbing_01) — C2 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 30 | 4 | 8 | 3 | 1 | 46 | 0.968 | 0.652 | 0.779 |
| CLARIFY | 1 | 5 | 0 | 1 | 0 | 7 | 0.417 | 0.714 | 0.526 |
| ABSTAIN | 0 | 1 | 5 | 0 | 0 | 6 | 0.385 | 0.833 | 0.526 |
| WARN | 0 | 2 | 0 | 7 | 0 | 9 | 0.636 | 0.778 | 0.700 |

### Development (cafe_01 + plumbing_01) — C3 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 37 | 7 | 0 | 0 | 2 | 46 | 0.974 | 0.804 | 0.881 |
| CLARIFY | 1 | 6 | 0 | 0 | 0 | 7 | 0.400 | 0.857 | 0.545 |
| ABSTAIN | 0 | 0 | 6 | 0 | 0 | 6 | 1.000 | 1.000 | 1.000 |
| WARN | 0 | 2 | 0 | 7 | 0 | 9 | 1.000 | 0.778 | 0.875 |

### Development (cafe_01 + plumbing_01) — C4 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 39 | 5 | 0 | 0 | 2 | 46 | 0.975 | 0.848 | 0.907 |
| CLARIFY | 1 | 5 | 0 | 0 | 1 | 7 | 0.455 | 0.714 | 0.556 |
| ABSTAIN | 0 | 0 | 6 | 0 | 0 | 6 | 1.000 | 1.000 | 1.000 |
| WARN | 0 | 1 | 0 | 8 | 0 | 9 | 1.000 | 0.889 | 0.941 |

## Expanded development (bakery_01 + clinic_01)

Majority-class baseline: `ANSWER` (36/53 = 67.9%).

| Config | Turns | Accuracy | Majority baseline | vs Majority | Macro-F1 | ANSWER F1 | CLARIFY F1 | ABSTAIN F1 | WARN F1 | Unparsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 53 | 84.9% | 67.9% | +17.0% | 0.775 | 0.914 | 0.727 | 0.857 | 0.600 | 1 |
| C1 | 53 | 83.0% | 67.9% | +15.1% | 0.738 | 0.912 | 0.667 | 0.706 | 0.667 | 0 |
| C2 | 53 | 81.1% | 67.9% | +13.2% | 0.707 | 0.909 | 0.667 | 0.706 | 0.545 | 0 |
| C3 | 53 | 73.6% | 67.9% | +5.7% | 0.635 | 0.853 | 0.600 | 0.421 | 0.667 | 0 |
| C4 | 53 | 77.4% | 67.9% | +9.4% | 0.699 | 0.857 | 0.800 | 0.471 | 0.667 | 0 |

### Expanded development (bakery_01 + clinic_01) — C0 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 32 | 1 | 0 | 2 | 1 | 36 | 0.941 | 0.889 | 0.914 |
| CLARIFY | 2 | 4 | 0 | 0 | 0 | 6 | 0.800 | 0.667 | 0.727 |
| ABSTAIN | 0 | 0 | 6 | 2 | 0 | 8 | 1.000 | 0.750 | 0.857 |
| WARN | 0 | 0 | 0 | 3 | 0 | 3 | 0.429 | 1.000 | 0.600 |

### Expanded development (bakery_01 + clinic_01) — C1 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 31 | 2 | 2 | 1 | 0 | 36 | 0.969 | 0.861 | 0.912 |
| CLARIFY | 1 | 4 | 1 | 0 | 0 | 6 | 0.667 | 0.667 | 0.667 |
| ABSTAIN | 0 | 0 | 6 | 2 | 0 | 8 | 0.667 | 0.750 | 0.706 |
| WARN | 0 | 0 | 0 | 3 | 0 | 3 | 0.500 | 1.000 | 0.667 |

### Expanded development (bakery_01 + clinic_01) — C2 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 30 | 2 | 1 | 3 | 0 | 36 | 1.000 | 0.833 | 0.909 |
| CLARIFY | 0 | 4 | 2 | 0 | 0 | 6 | 0.667 | 0.667 | 0.667 |
| ABSTAIN | 0 | 0 | 6 | 2 | 0 | 8 | 0.667 | 0.750 | 0.706 |
| WARN | 0 | 0 | 0 | 3 | 0 | 3 | 0.375 | 1.000 | 0.545 |

### Expanded development (bakery_01 + clinic_01) — C3 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 29 | 1 | 5 | 1 | 0 | 36 | 0.906 | 0.806 | 0.853 |
| CLARIFY | 1 | 3 | 2 | 0 | 0 | 6 | 0.750 | 0.500 | 0.600 |
| ABSTAIN | 2 | 0 | 4 | 2 | 0 | 8 | 0.364 | 0.500 | 0.421 |
| WARN | 0 | 0 | 0 | 3 | 0 | 3 | 0.500 | 1.000 | 0.667 |

### Expanded development (bakery_01 + clinic_01) — C4 confusion matrix and per-class P/R/F1

| Expected \ Pred | ANSWER | CLARIFY | ABSTAIN | WARN | UNPARSED | Support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER | 30 | 0 | 5 | 1 | 0 | 36 | 0.882 | 0.833 | 0.857 |
| CLARIFY | 2 | 4 | 0 | 0 | 0 | 6 | 1.000 | 0.667 | 0.800 |
| ABSTAIN | 2 | 0 | 4 | 2 | 0 | 8 | 0.444 | 0.500 | 0.471 |
| WARN | 0 | 0 | 0 | 3 | 0 | 3 | 0.500 | 1.000 | 0.667 |
