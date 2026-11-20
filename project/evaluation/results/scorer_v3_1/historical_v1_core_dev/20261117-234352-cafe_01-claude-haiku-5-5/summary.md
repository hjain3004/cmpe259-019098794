# Run 20261117-234352-cafe_01-claude-haiku-5-5 (scorer_v3_1)

Model `claude-haiku-5-5`, prompt `answer_system_v1`, commit `081b05c`, scenario `cafe_01`, 21 conversations, 28 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 19/28 (68%) | 14/21 | 71% | 100% | 27/28 | 8.82 | 7492 |
| C1 | 12/28 (43%) | 6/21 | 46% | 77% | 28/28 | 7.27 | 4502 |
| C2 | 15/28 (54%) | 8/21 | 61% | 83% | 28/28 | 6.97 | 4150 |
| C3 | 20/28 (71%) | 14/21 | 79% | 94% | 28/28 | 5.11 | 11306 |
| C4 | 20/28 (71%) | 14/21 | 79% | 91% | 28/28 | 5.61 | 10565 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 5/21 (24%) | 0/18 (0%) |
| C1 | 6/21 (29%) | 7/18 (39%) |
| C2 | 7/21 (33%) | 4/18 (22%) |
| C3 | 3/21 (14%) | 1/18 (6%) |
| C4 | 4/21 (19%) | 1/18 (6%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.371 | 5.22 | 83 | 169 | 78% |
| C1 | 0.636 | 0.286 | 3.93 | 95 | 138 | 82% |
| C2 | 0.727 | 0.343 | 4.14 | 96 | 123 | 86% |
| C3 | 0.909 | 0.698 | 4.39 | 70 | 122 | 89% |
| C4 | 0.864 | 0.648 | 3.93 | 70 | 142 | 86% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 2/4 | 1/4 | 2/4 | 3/4 | 3/4 |
| aggregation | 5/8 | 2/8 | 2/8 | 6/8 | 6/8 |
| temporal | 4/7 | 2/7 | 2/7 | 6/7 | 6/7 |
| linking | 6/10 | 3/10 | 6/10 | 5/10 | 5/10 |
| comparison | 6/7 | 4/7 | 4/7 | 5/7 | 5/7 |
| dialogue | 7/11 | 6/11 | 7/11 | 8/11 | 8/11 |
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
| Q11 | pass | pass | pass | fail | fail |
| Q12 | pass | pass | pass | pass | pass |
| Q13 | fail | fail | fail | fail | fail |
| Q14 | fail | fail | fail | pass | pass |
| Q15 | pass | fail | fail | pass | pass |
| Q16 | pass | fail | pass | pass | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | pass | fail | fail | pass | pass |
| Q19 | pass | fail | fail | pass | pass |
| Q20 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |
