# Run 20261118-231330-bakery_01-claude-haiku-5-5

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `7a5dd10`, scenario `bakery_01`, 18 conversations, 27 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 18/27 (67%) | 11/18 | 82% | 91% | 27/27 | 6.04 | 8287 |
| C1 | 15/27 (56%) | 7/18 | 74% | 84% | 27/27 | 5.48 | 5044 |
| C2 | 15/27 (56%) | 10/18 | 74% | 82% | 27/27 | 5.09 | 4668 |
| C3 | 15/27 (56%) | 9/18 | 70% | 82% | 27/27 | 6.03 | 15278 |
| C4 | 16/27 (59%) | 10/18 | 74% | 82% | 27/27 | 5.94 | 14112 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 1/21 (5%) | 0/17 (0%) |
| C1 | 1/21 (5%) | 2/17 (12%) |
| C2 | 2/21 (10%) | 1/17 (6%) |
| C3 | 0/21 (0%) | 2/17 (12%) |
| C4 | 1/21 (5%) | 2/17 (12%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 0.984 | 0.533 | 3.59 | 69 | 104 | 96% |
| C1 | 0.853 | 0.500 | 3.33 | 75 | 103 | 96% |
| C2 | 0.901 | 0.551 | 3.30 | 76 | 95 | 100% |
| C3 | 0.758 | 0.667 | 3.15 | 64 | 89 | 100% |
| C4 | 0.806 | 0.710 | 3.63 | 65 | 104 | 100% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 |
| aggregation | 7/7 | 4/7 | 5/7 | 7/7 | 7/7 |
| temporal | 7/10 | 7/10 | 7/10 | 7/10 | 8/10 |
| linking | 9/14 | 8/14 | 8/14 | 8/14 | 8/14 |
| comparison | 3/7 | 3/7 | 3/7 | 4/7 | 3/7 |
| dialogue | 9/15 | 10/15 | 7/15 | 8/15 | 8/15 |
| abstention | 2/2 | 2/2 | 2/2 | 1/2 | 1/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| D101 | pass | fail | pass | pass | pass |
| D102 | pass | fail | fail | pass | pass |
| D103 | pass | pass | pass | pass | pass |
| D104 | pass | pass | pass | fail | fail |
| D105 | pass | fail | pass | fail | pass |
| D106 | fail | fail | pass | fail | fail |
| D107 | fail | fail | fail | pass | pass |
| D108 | fail | pass | fail | fail | fail |
| D109 | pass | fail | fail | pass | pass |
| D110 | pass | pass | pass | fail | fail |
| D111 | pass | fail | pass | pass | pass |
| D112 | pass | pass | pass | pass | pass |
| D113 | fail | fail | fail | fail | fail |
| D114 | pass | pass | pass | pass | pass |
| D115 | fail | pass | pass | pass | pass |
| D116 | pass | fail | fail | fail | fail |
| D117 | fail | fail | fail | fail | fail |
| D118 | fail | fail | fail | fail | fail |
