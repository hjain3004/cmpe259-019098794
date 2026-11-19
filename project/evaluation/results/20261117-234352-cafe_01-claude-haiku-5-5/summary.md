# Run 20261117-234352-cafe_01-claude-haiku-5-5

Model `claude-haiku-5-5`, prompt `answer_system_v1`, commit `081b05c`, scenario `cafe_01`, 21 conversations, 28 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 19/28 (68%) | 14/21 | 71% | 100% | 27/28 | 8.82 | 7492 |
| C1 | 12/28 (43%) | 6/21 | 46% | 77% | 28/28 | 7.27 | 4502 |
| C2 | 14/28 (50%) | 8/21 | 61% | 80% | 28/28 | 6.97 | 4150 |
| C3 | 18/28 (64%) | 12/21 | 75% | 94% | 27/28 | 5.11 | 11306 |
| C4 | 19/28 (68%) | 13/21 | 79% | 91% | 28/28 | 5.61 | 10565 |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.371 | 5.22 | 83 | 169 | 78% |
| C1 | 0.636 | 0.286 | 3.93 | 95 | 138 | 82% |
| C2 | 0.727 | 0.343 | 4.14 | 96 | 123 | 86% |
| C3 | 0.905 | 0.722 | 4.33 | 69 | 122 | 89% |
| C4 | 0.864 | 0.648 | 3.93 | 70 | 142 | 86% |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | fail | fail | fail | fail | pass |
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
| Q18 | pass | fail | fail | fail | fail |
| Q19 | pass | fail | fail | pass | pass |
| Q20 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |
