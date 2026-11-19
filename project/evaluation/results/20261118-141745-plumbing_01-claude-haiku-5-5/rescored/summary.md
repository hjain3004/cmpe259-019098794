# Run 20261118-141745-plumbing_01-claude-haiku-5-5 (rescored)

Model `claude-haiku-5-5`, prompt `answer_system_v1`, commit `081b05c`, scenario `plumbing_01`, 30 conversations, 40 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 24/40 (60%) | 17/30 | 70% | 90% | 36/40 | 7.94 | 9020 |
| C1 | 15/40 (38%) | 12/30 | 52% | 66% | 38/40 | 7.67 | 4830 |
| C2 | 20/40 (50%) | 13/30 | 60% | 82% | 40/40 | 6.88 | 4458 |
| C3 | 25/40 (62%) | 18/30 | 65% | 84% | 40/40 | 6.04 | 13054 |
| C4 | 21/40 (52%) | 14/30 | 55% | 79% | 40/40 | 6.04 | 11551 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 5/32 (16%) | 1/28 (4%) |
| C1 | 7/32 (22%) | 6/28 (21%) |
| C2 | 10/32 (31%) | 4/28 (14%) |
| C3 | 7/32 (22%) | 0/28 (0%) |
| C4 | 11/32 (34%) | 0/28 (0%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 0.992 | 0.458 | 4.92 | 84 | 141 | 81% |
| C1 | 0.591 | 0.335 | 4.11 | 96 | 148 | 74% |
| C2 | 0.784 | 0.458 | 4.10 | 80 | 126 | 85% |
| C3 | 0.838 | 0.572 | 4.85 | 65 | 140 | 82% |
| C4 | 0.779 | 0.552 | 5.12 | 72 | 132 | 80% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 2/4 | 1/4 | 1/4 | 1/4 | 1/4 |
| aggregation | 7/11 | 4/11 | 4/11 | 8/11 | 6/11 |
| temporal | 5/10 | 4/10 | 3/10 | 6/10 | 5/10 |
| linking | 8/13 | 5/13 | 7/13 | 8/13 | 7/13 |
| comparison | 9/13 | 6/13 | 7/13 | 8/13 | 7/13 |
| dialogue | 9/16 | 4/16 | 8/16 | 9/16 | 7/16 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | fail | fail | fail | fail | fail |
| Q02 | fail | fail | fail | pass | fail |
| Q03 | fail | fail | fail | fail | fail |
| Q04 | fail | fail | fail | pass | pass |
| Q05 | fail | fail | fail | fail | fail |
| Q06 | fail | fail | fail | fail | fail |
| Q07 | pass | fail | pass | pass | pass |
| Q08 | pass | pass | pass | pass | pass |
| Q09 | pass | fail | pass | pass | pass |
| Q10 | pass | fail | fail | pass | fail |
| Q11 | pass | pass | pass | pass | fail |
| Q12 | pass | pass | pass | pass | pass |
| Q13 | fail | fail | fail | fail | fail |
| Q14 | pass | pass | pass | pass | pass |
| Q15 | pass | pass | pass | pass | pass |
| Q16 | pass | fail | fail | fail | fail |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | pass | pass | pass | fail | fail |
| Q19 | pass | fail | fail | pass | fail |
| Q20 | fail | fail | fail | fail | fail |
| Q21 | fail | fail | fail | pass | fail |
| Q22 | fail | fail | fail | fail | fail |
| Q23 | fail | pass | fail | pass | pass |
| Q24 | pass | fail | fail | pass | pass |
| Q25 | pass | pass | pass | pass | pass |
| Q26 | pass | pass | pass | pass | pass |
| Q27 | pass | pass | pass | fail | pass |
| Q28 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |
