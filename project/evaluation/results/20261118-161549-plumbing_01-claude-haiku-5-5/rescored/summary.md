# Run 20261118-161549-plumbing_01-claude-haiku-5-5 (rescored)

Model `claude-haiku-5-5`, prompt `answer_system_v1`, commit `081b05c`, scenario `plumbing_01`, 30 conversations, 40 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 23/40 (57%) | 16/30 | 65% | 95% | 38/40 | 6.55 | 8928 |
| C1 | 14/40 (35%) | 10/30 | 48% | 64% | 40/40 | 7.71 | 4776 |
| C2 | 22/40 (55%) | 15/30 | 57% | 78% | 40/40 | 6.51 | 4470 |
| C3 | 21/40 (52%) | 13/30 | 55% | 83% | 38/40 | 6.46 | 13431 |
| C4 | 23/40 (57%) | 15/30 | 62% | 82% | 39/40 | 6.55 | 12465 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 10/32 (31%) | 0/28 (0%) |
| C1 | 10/32 (31%) | 6/28 (21%) |
| C2 | 7/32 (22%) | 6/28 (21%) |
| C3 | 10/32 (31%) | 0/28 (0%) |
| C4 | 10/32 (31%) | 0/28 (0%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.448 | 4.68 | 82 | 160 | 79% |
| C1 | 0.574 | 0.312 | 4.50 | 90 | 146 | 82% |
| C2 | 0.770 | 0.435 | 4.25 | 83 | 129 | 80% |
| C3 | 0.833 | 0.572 | 5.50 | 86 | 126 | 87% |
| C4 | 0.818 | 0.569 | 5.44 | 77 | 162 | 77% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 2/4 | 1/4 | 1/4 | 1/4 | 2/4 |
| aggregation | 7/11 | 4/11 | 6/11 | 5/11 | 4/11 |
| temporal | 5/10 | 2/10 | 6/10 | 4/10 | 5/10 |
| linking | 7/13 | 4/13 | 8/13 | 6/13 | 8/13 |
| comparison | 7/13 | 5/13 | 7/13 | 9/13 | 8/13 |
| dialogue | 9/16 | 5/16 | 7/16 | 8/16 | 9/16 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | fail | fail | fail | fail | fail |
| Q02 | fail | fail | fail | fail | fail |
| Q03 | fail | fail | fail | fail | fail |
| Q04 | fail | fail | fail | pass | pass |
| Q05 | fail | fail | pass | fail | fail |
| Q06 | fail | fail | fail | fail | fail |
| Q07 | pass | fail | pass | pass | pass |
| Q08 | pass | pass | pass | pass | pass |
| Q09 | pass | fail | pass | pass | pass |
| Q10 | fail | fail | fail | pass | fail |
| Q11 | pass | pass | pass | fail | pass |
| Q12 | pass | pass | pass | pass | pass |
| Q13 | fail | fail | fail | fail | fail |
| Q14 | pass | pass | pass | pass | pass |
| Q15 | pass | pass | pass | pass | pass |
| Q16 | pass | fail | fail | fail | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | fail | pass | fail | fail | pass |
| Q19 | pass | fail | fail | fail | fail |
| Q20 | fail | fail | fail | fail | fail |
| Q21 | pass | fail | fail | fail | fail |
| Q22 | fail | fail | fail | fail | fail |
| Q23 | fail | fail | pass | pass | pass |
| Q24 | pass | fail | pass | pass | fail |
| Q25 | pass | pass | pass | fail | fail |
| Q26 | pass | pass | pass | pass | pass |
| Q27 | pass | fail | pass | fail | pass |
| Q28 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |
