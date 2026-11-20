# Run 20261118-224539-plumbing_01-claude-haiku-5-5 (scorer_v3)

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `7a5dd10`, scenario `plumbing_01`, 30 conversations, 40 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 26/40 (65%) | 20/30 | 78% | 90% | 39/40 | 6.55 | 9510 |
| C1 | 14/40 (35%) | 11/30 | 57% | 66% | 39/40 | 6.11 | 5310 |
| C2 | 24/40 (60%) | 17/30 | 70% | 82% | 39/40 | 5.84 | 4971 |
| C3 | 31/40 (78%) | 23/30 | 82% | 83% | 39/40 | 4.62 | 11517 |
| C4 | 33/40 (82%) | 25/30 | 88% | 85% | 40/40 | 4.82 | 12231 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 3/32 (9%) | 0/28 (0%) |
| C1 | 2/32 (6%) | 8/28 (29%) |
| C2 | 1/32 (3%) | 5/28 (18%) |
| C3 | 0/32 (0%) | 0/28 (0%) |
| C4 | 0/32 (0%) | 0/28 (0%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 0.962 | 0.477 | 4.46 | 78 | 121 | 90% |
| C1 | 0.574 | 0.344 | 3.72 | 92 | 134 | 82% |
| C2 | 0.770 | 0.472 | 3.79 | 85 | 126 | 82% |
| C3 | 0.793 | 0.658 | 3.64 | 55 | 103 | 100% |
| C4 | 0.814 | 0.640 | 3.75 | 66 | 103 | 95% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 2/4 | 1/4 | 2/4 | 4/4 | 4/4 |
| aggregation | 8/11 | 4/11 | 6/11 | 9/11 | 10/11 |
| temporal | 8/10 | 2/10 | 7/10 | 10/10 | 10/10 |
| linking | 10/13 | 4/13 | 8/13 | 10/13 | 10/13 |
| comparison | 7/13 | 6/13 | 9/13 | 9/13 | 11/13 |
| dialogue | 8/16 | 3/16 | 8/16 | 10/16 | 11/16 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | fail | fail | pass | pass | pass |
| Q02 | pass | fail | fail | pass | pass |
| Q03 | pass | fail | fail | pass | pass |
| Q04 | pass | fail | fail | pass | pass |
| Q05 | pass | pass | pass | pass | pass |
| Q06 | pass | fail | fail | pass | pass |
| Q07 | pass | fail | pass | pass | pass |
| Q08 | pass | pass | pass | pass | pass |
| Q09 | pass | fail | pass | pass | pass |
| Q10 | pass | fail | fail | pass | pass |
| Q11 | pass | pass | pass | fail | fail |
| Q12 | pass | pass | pass | pass | pass |
| Q13 | fail | fail | fail | fail | pass |
| Q14 | pass | pass | pass | pass | pass |
| Q15 | pass | pass | pass | pass | pass |
| Q16 | fail | fail | fail | pass | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | pass | fail | pass | fail | pass |
| Q19 | pass | fail | fail | pass | pass |
| Q20 | fail | fail | fail | fail | fail |
| Q21 | fail | fail | fail | pass | pass |
| Q22 | fail | fail | fail | fail | fail |
| Q23 | fail | fail | pass | pass | pass |
| Q24 | fail | pass | pass | pass | pass |
| Q25 | pass | pass | pass | pass | pass |
| Q26 | pass | pass | pass | pass | pass |
| Q27 | pass | fail | pass | pass | pass |
| Q28 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |
