# Citation Precision, Recall, and F1

Computed over scored turns with gold citations, reporting mean per-turn citation recall/precision/F1 and corpus micro-F1.

## Held-out (landscaping_01)

| Config | Turns w/ gold cites | Mean recall | Mean precision | Mean F1 | Micro-F1 (P / R) |
| --- | --- | --- | --- | --- | --- |
| C0 | 32 | 1.000 | 0.541 | 0.660 | 0.570 (0.399 / 1.000) |
| C1 | 34 | 0.571 | 0.366 | 0.429 | 0.400 (0.308 / 0.571) |
| C2 | 33 | 0.672 | 0.473 | 0.536 | 0.491 (0.377 / 0.705) |
| C3 | 33 | 0.838 | 0.611 | 0.683 | 0.724 (0.611 / 0.887) |
| C4 | 33 | 0.747 | 0.552 | 0.617 | 0.685 (0.586 / 0.823) |

## Development (cafe_01 + plumbing_01)

| Config | Turns w/ gold cites | Mean recall | Mean precision | Mean F1 | Micro-F1 (P / R) |
| --- | --- | --- | --- | --- | --- |
| C0 | 54 | 0.977 | 0.471 | 0.609 | 0.566 (0.398 / 0.979) |
| C1 | 56 | 0.598 | 0.330 | 0.406 | 0.397 (0.295 / 0.608) |
| C2 | 55 | 0.744 | 0.428 | 0.517 | 0.497 (0.369 / 0.758) |
| C3 | 54 | 0.799 | 0.653 | 0.698 | 0.721 (0.620 / 0.860) |
| C4 | 54 | 0.846 | 0.657 | 0.718 | 0.739 (0.630 / 0.895) |

## Expanded development (bakery_01 + clinic_01)

| Config | Turns w/ gold cites | Mean recall | Mean precision | Mean F1 | Micro-F1 (P / R) |
| --- | --- | --- | --- | --- | --- |
| C0 | 42 | 0.992 | 0.588 | 0.708 | 0.710 (0.554 / 0.989) |
| C1 | 43 | 0.864 | 0.551 | 0.642 | 0.625 (0.503 / 0.824) |
| C2 | 43 | 0.901 | 0.600 | 0.694 | 0.675 (0.548 / 0.879) |
| C3 | 43 | 0.777 | 0.712 | 0.709 | 0.751 (0.698 / 0.813) |
| C4 | 43 | 0.785 | 0.723 | 0.721 | 0.758 (0.701 / 0.824) |
