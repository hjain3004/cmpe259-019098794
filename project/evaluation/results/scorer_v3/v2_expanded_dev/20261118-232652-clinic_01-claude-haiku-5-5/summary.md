# Run 20261118-232652-clinic_01-claude-haiku-5-5 (scorer_v3)

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `7a5dd10`, scenario `clinic_01`, 18 conversations, 26 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 19/26 (73%) | 12/18 | 88% | 94% | 25/26 | 5.34 | 8313 |
| C1 | 12/26 (46%) | 7/18 | 92% | 71% | 26/26 | 4.46 | 4682 |
| C2 | 12/26 (46%) | 6/18 | 88% | 73% | 26/26 | 5.3 | 4408 |
| C3 | 15/26 (58%) | 9/18 | 77% | 83% | 26/26 | 5.21 | 14487 |
| C4 | 15/26 (58%) | 9/18 | 81% | 85% | 26/26 | 5.73 | 14486 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 1/21 (5%) | 0/19 (0%) |
| C1 | 0/21 (0%) | 0/19 (0%) |
| C2 | 1/21 (5%) | 0/19 (0%) |
| C3 | 1/21 (5%) | 3/19 (16%) |
| C4 | 0/21 (0%) | 3/19 (16%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.642 | 3.36 | 65 | 99 | 100% |
| C1 | 0.875 | 0.600 | 3.15 | 61 | 100 | 96% |
| C2 | 0.902 | 0.646 | 3.08 | 78 | 102 | 96% |
| C3 | 0.795 | 0.755 | 3.62 | 59 | 91 | 100% |
| C4 | 0.765 | 0.735 | 3.73 | 63 | 98 | 100% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 4/4 | 2/4 | 2/4 | 4/4 | 4/4 |
| aggregation | 9/10 | 4/10 | 4/10 | 6/10 | 7/10 |
| temporal | 3/5 | 3/5 | 2/5 | 3/5 | 3/5 |
| linking | 13/16 | 8/16 | 8/16 | 10/16 | 10/16 |
| comparison | 3/6 | 3/6 | 3/6 | 3/6 | 3/6 |
| dialogue | 10/14 | 7/14 | 8/14 | 7/14 | 8/14 |
| abstention | 3/3 | 2/3 | 2/3 | 3/3 | 2/3 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| D201 | pass | fail | fail | pass | pass |
| D202 | fail | fail | pass | fail | fail |
| D203 | pass | pass | fail | pass | pass |
| D204 | pass | pass | pass | fail | fail |
| D205 | pass | fail | fail | pass | fail |
| D206 | pass | pass | pass | pass | pass |
| D207 | pass | fail | fail | pass | pass |
| D208 | fail | fail | fail | pass | pass |
| D209 | pass | fail | fail | pass | pass |
| D210 | pass | pass | pass | fail | fail |
| D211 | fail | fail | fail | fail | fail |
| D212 | pass | pass | fail | pass | pass |
| D213 | fail | fail | fail | fail | fail |
| D214 | pass | fail | pass | fail | fail |
| D215 | pass | fail | fail | fail | pass |
| D216 | fail | pass | fail | fail | fail |
| D217 | pass | pass | pass | pass | pass |
| D218 | fail | fail | fail | fail | fail |
