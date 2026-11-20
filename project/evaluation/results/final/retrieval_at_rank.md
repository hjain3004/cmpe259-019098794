# Document-Level Retrieval at Rank for C1 and C2 (QA Lecture)

Precision@k, Recall@k (k = 1, 3, 5, 8), and Mean Reciprocal Rank (MRR) of the first gold evidence document.

## Held-out (landscaping_01)

| Config | Turns w/ gold | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 34 | 0.206 | 0.176 | 0.129 | 0.132 | 0.176 | 0.368 | 0.407 | 0.571 | 0.364 |
| C2 | 34 | 0.265 | 0.255 | 0.200 | 0.158 | 0.213 | 0.414 | 0.547 | 0.652 | 0.441 |

## Development (cafe_01 + plumbing_01)

| Config | Turns w/ gold | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 56 | 0.268 | 0.185 | 0.146 | 0.136 | 0.205 | 0.362 | 0.466 | 0.625 | 0.420 |
| C2 | 56 | 0.143 | 0.190 | 0.204 | 0.167 | 0.116 | 0.365 | 0.589 | 0.757 | 0.376 |

## Expanded development (bakery_01 + clinic_01)

| Config | Turns w/ gold | P@1 | P@3 | P@5 | P@8 | R@1 | R@3 | R@5 | R@8 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 43 | 0.535 | 0.403 | 0.335 | 0.233 | 0.337 | 0.609 | 0.804 | 0.897 | 0.687 |
| C2 | 43 | 0.442 | 0.380 | 0.316 | 0.241 | 0.279 | 0.560 | 0.729 | 0.919 | 0.630 |
