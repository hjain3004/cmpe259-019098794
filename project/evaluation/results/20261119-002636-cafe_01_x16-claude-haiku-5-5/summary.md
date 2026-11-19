# Run 20261119-002636-cafe_01_x16-claude-haiku-5-5

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `7a5dd10`, scenario `cafe_01_x16`, 21 conversations, 28 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 21/28 (75%) | 16/21 | 82% | 91% | 27/28 | 8.91 | 62973 |
| C1 | 9/28 (32%) | 6/21 | 50% | 57% | 28/28 | 5.02 | 4618 |
| C2 | 7/28 (25%) | 4/21 | 50% | 46% | 27/28 | 5.73 | 4318 |
| C3 | 21/28 (75%) | 16/21 | 82% | 89% | 28/28 | 5.02 | 17053 |
| C4 | 20/28 (71%) | 16/21 | 75% | 91% | 26/28 | 5.15 | 18594 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 1/21 (5%) | 0/18 (0%) |
| C1 | 1/21 (5%) | 10/18 (56%) |
| C2 | 0/21 (0%) | 10/18 (56%) |
| C3 | 0/21 (0%) | 0/18 (0%) |
| C4 | 0/21 (0%) | 0/18 (0%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.423 | 4.33 | 78 | 141 | 89% |
| C1 | 0.341 | 0.260 | 2.71 | 78 | 110 | 96% |
| C2 | 0.273 | 0.235 | 3.22 | 74 | 110 | 96% |
| C3 | 0.795 | 0.629 | 3.86 | 69 | 100 | 96% |
| C4 | 0.881 | 0.648 | 3.77 | 66 | 108 | 100% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 3/4 | 1/4 | 1/4 | 4/4 | 4/4 |
| aggregation | 7/8 | 1/8 | 0/8 | 6/8 | 5/8 |
| temporal | 6/7 | 1/7 | 0/7 | 6/7 | 5/7 |
| linking | 6/10 | 4/10 | 2/10 | 6/10 | 7/10 |
| comparison | 6/7 | 1/7 | 2/7 | 6/7 | 5/7 |
| dialogue | 7/11 | 3/11 | 3/11 | 6/11 | 4/11 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | pass | fail | fail | pass | pass |
| Q02 | pass | fail | fail | pass | pass |
| Q03 | fail | fail | fail | pass | pass |
| Q04 | fail | fail | fail | pass | pass |
| Q06 | pass | fail | fail | pass | pass |
| Q07 | pass | fail | fail | pass | pass |
| Q08 | pass | pass | pass | pass | pass |
| Q09 | pass | pass | fail | pass | pass |
| Q10 | pass | fail | fail | pass | pass |
| Q11 | pass | pass | pass | fail | pass |
| Q12 | pass | pass | fail | pass | pass |
| Q13 | fail | fail | fail | fail | fail |
| Q14 | pass | fail | fail | pass | pass |
| Q15 | pass | fail | fail | pass | pass |
| Q16 | pass | fail | fail | pass | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | pass | fail | fail | pass | fail |
| Q19 | pass | fail | fail | fail | fail |
| Q20 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |
