# Run 20261117-154644-cafe_01-claude-haiku-5-5 (rescored)

Model `claude-haiku-5-5`, prompt `answer_system_v1`, commit `1e94e92`, scenario `cafe_01`, 21 conversations, 28 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 14/28 (50%) | 7/21 | 54% | 77% | 28/28 | 7.15 | 4524 |
| C2 | 12/28 (43%) | 8/21 | 57% | 80% | 28/28 | 7.26 | 4248 |
| C3 | 19/28 (68%) | 14/21 | 75% | 91% | 26/28 | 5.27 | 11491 |
| C4 | 18/28 (64%) | 14/21 | 79% | 91% | 28/28 | 5.46 | 10915 |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 0.636 | 0.297 | 4.11 | 88 | 161 | 71% |
| C2 | 0.727 | 0.329 | 4.64 | 89 | 128 | 82% |
| C3 | 0.900 | 0.647 | 3.62 | 64 | 93 | 100% |
| C4 | 0.955 | 0.682 | 4.21 | 69 | 102 | 96% |

## Conversation success

| Conversation | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- |
| Q01 | fail | fail | pass | pass |
| Q02 | fail | fail | pass | pass |
| Q03 | fail | fail | pass | fail |
| Q04 | fail | fail | pass | pass |
| Q06 | fail | fail | fail | fail |
| Q07 | pass | pass | pass | pass |
| Q08 | pass | pass | fail | fail |
| Q09 | pass | pass | pass | pass |
| Q10 | fail | fail | pass | pass |
| Q11 | pass | pass | fail | fail |
| Q12 | pass | pass | pass | pass |
| Q13 | fail | fail | fail | pass |
| Q14 | fail | fail | pass | pass |
| Q15 | fail | fail | pass | pass |
| Q16 | fail | pass | pass | pass |
| Q17 | fail | fail | fail | fail |
| Q18 | fail | fail | fail | fail |
| Q19 | fail | fail | pass | pass |
| Q20 | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass |
