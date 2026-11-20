# Run 20261118-164027-cafe_01-claude-haiku-5-5 (scorer_v3_1)

Model `claude-haiku-5-5`, prompt `answer_system_v1`, commit `081b05c`, scenario `cafe_01`, 21 conversations, 28 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 17/28 (61%) | 12/21 | 61% | 94% | 27/28 | 8.56 | 7614 |
| C1 | 13/28 (46%) | 7/21 | 46% | 74% | 28/28 | 7.37 | 4469 |
| C2 | 14/28 (50%) | 8/21 | 57% | 83% | 28/28 | 7.17 | 4190 |
| C3 | 21/28 (75%) | 15/21 | 75% | 97% | 28/28 | 5.8 | 11180 |
| C4 | 21/28 (75%) | 15/21 | 82% | 100% | 28/28 | 6.52 | 10982 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 8/21 (38%) | 0/18 (0%) |
| C1 | 6/21 (29%) | 8/18 (44%) |
| C2 | 8/21 (38%) | 4/18 (22%) |
| C3 | 4/21 (19%) | 1/18 (6%) |
| C4 | 4/21 (19%) | 0/18 (0%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.406 | 5.59 | 78 | 160 | 82% |
| C1 | 0.636 | 0.257 | 4.25 | 99 | 139 | 82% |
| C2 | 0.727 | 0.338 | 4.11 | 86 | 137 | 86% |
| C3 | 0.955 | 0.661 | 4.86 | 78 | 125 | 89% |
| C4 | 0.955 | 0.691 | 5.00 | 72 | 141 | 82% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 2/4 | 1/4 | 2/4 | 3/4 | 3/4 |
| aggregation | 3/8 | 2/8 | 2/8 | 6/8 | 6/8 |
| temporal | 3/7 | 2/7 | 2/7 | 6/7 | 6/7 |
| linking | 6/10 | 3/10 | 5/10 | 6/10 | 6/10 |
| comparison | 6/7 | 5/7 | 4/7 | 5/7 | 5/7 |
| dialogue | 6/11 | 7/11 | 6/11 | 8/11 | 8/11 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | fail | fail | fail | pass | pass |
| Q02 | pass | fail | fail | pass | pass |
| Q03 | fail | fail | fail | fail | fail |
| Q04 | pass | fail | fail | pass | pass |
| Q06 | fail | fail | fail | fail | fail |
| Q07 | pass | pass | pass | pass | pass |
| Q08 | pass | pass | pass | pass | pass |
| Q09 | pass | fail | pass | pass | pass |
| Q10 | pass | fail | fail | fail | fail |
| Q11 | pass | pass | pass | pass | pass |
| Q12 | pass | pass | pass | pass | pass |
| Q13 | fail | fail | fail | fail | fail |
| Q14 | fail | fail | fail | pass | pass |
| Q15 | fail | fail | fail | pass | pass |
| Q16 | pass | fail | pass | pass | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | pass | pass | fail | pass | pass |
| Q19 | fail | fail | fail | pass | pass |
| Q20 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |
