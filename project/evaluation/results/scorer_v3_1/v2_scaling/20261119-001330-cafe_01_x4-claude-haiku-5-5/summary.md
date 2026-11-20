# Run 20261119-001330-cafe_01_x4-claude-haiku-5-5 (scorer_v3_1)

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `7a5dd10`, scenario `cafe_01_x4`, 21 conversations, 28 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 22/28 (79%) | 17/21 | 86% | 94% | 28/28 | 7.31 | 19061 |
| C1 | 11/28 (39%) | 6/21 | 57% | 63% | 28/28 | 5.21 | 4648 |
| C2 | 6/28 (21%) | 4/21 | 43% | 49% | 28/28 | 5.24 | 4300 |
| C3 | 24/28 (86%) | 18/21 | 89% | 91% | 28/28 | 5.11 | 13743 |
| C4 | 23/28 (82%) | 17/21 | 86% | 94% | 28/28 | 5.6 | 13885 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 1/21 (5%) | 0/18 (0%) |
| C1 | 1/21 (5%) | 8/18 (44%) |
| C2 | 1/21 (5%) | 10/18 (56%) |
| C3 | 0/21 (0%) | 0/18 (0%) |
| C4 | 0/21 (0%) | 0/18 (0%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.459 | 4.14 | 84 | 118 | 93% |
| C1 | 0.364 | 0.220 | 2.93 | 77 | 116 | 93% |
| C2 | 0.318 | 0.237 | 3.14 | 81 | 104 | 96% |
| C3 | 0.818 | 0.630 | 3.18 | 59 | 106 | 100% |
| C4 | 0.864 | 0.630 | 4.07 | 69 | 95 | 100% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 2/4 | 1/4 | 1/4 | 4/4 | 4/4 |
| aggregation | 8/8 | 2/8 | 0/8 | 8/8 | 7/8 |
| temporal | 5/7 | 2/7 | 0/7 | 7/7 | 6/7 |
| linking | 8/10 | 4/10 | 2/10 | 7/10 | 7/10 |
| comparison | 7/7 | 2/7 | 1/7 | 7/7 | 7/7 |
| dialogue | 7/11 | 5/11 | 2/11 | 8/11 | 7/11 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | fail | fail | fail | pass | pass |
| Q02 | pass | fail | fail | pass | pass |
| Q03 | fail | fail | fail | pass | pass |
| Q04 | pass | fail | fail | pass | pass |
| Q06 | pass | fail | fail | pass | pass |
| Q07 | pass | fail | fail | pass | pass |
| Q08 | pass | pass | pass | pass | pass |
| Q09 | pass | pass | fail | pass | pass |
| Q10 | pass | fail | fail | pass | pass |
| Q11 | pass | pass | pass | fail | fail |
| Q12 | pass | pass | fail | pass | pass |
| Q13 | pass | fail | fail | pass | pass |
| Q14 | pass | fail | fail | pass | pass |
| Q15 | pass | fail | fail | pass | pass |
| Q16 | pass | fail | fail | pass | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | pass | fail | fail | pass | pass |
| Q19 | pass | fail | fail | pass | fail |
| Q20 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |
