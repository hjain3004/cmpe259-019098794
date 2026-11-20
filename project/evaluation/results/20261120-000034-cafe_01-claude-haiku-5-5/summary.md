# Run 20261120-000034-cafe_01-claude-haiku-5-5

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `4f23435`, scenario `cafe_01`, 21 conversations, 28 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 21/28 (75%) | 15/21 | 86% | 91% | 28/28 | 7.0 | 7921 |
| C1 | 14/28 (50%) | 8/21 | 57% | 77% | 28/28 | 6.04 | 4944 |
| C2 | 17/28 (61%) | 10/21 | 79% | 80% | 28/28 | 5.9 | 4642 |
| C3 | 22/28 (79%) | 16/21 | 82% | 91% | 28/28 | 5.38 | 12478 |
| C4 | 24/28 (86%) | 18/21 | 89% | 91% | 28/28 | 5.07 | 11612 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 0/21 (0%) | 0/18 (0%) |
| C1 | 2/21 (10%) | 7/18 (39%) |
| C2 | 1/21 (5%) | 4/18 (22%) |
| C3 | 0/21 (0%) | 0/18 (0%) |
| C4 | 0/21 (0%) | 0/18 (0%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.436 | 4.75 | 69 | 111 | 93% |
| C1 | 0.591 | 0.325 | 3.57 | 75 | 113 | 93% |
| C2 | 0.727 | 0.364 | 3.68 | 74 | 120 | 89% |
| C3 | 0.864 | 0.676 | 3.75 | 70 | 106 | 100% |
| C4 | 0.864 | 0.668 | 3.36 | 58 | 91 | 100% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 2/4 | 1/4 | 2/4 | 4/4 | 4/4 |
| aggregation | 8/8 | 3/8 | 3/8 | 7/8 | 8/8 |
| temporal | 5/7 | 2/7 | 2/7 | 6/7 | 7/7 |
| linking | 7/10 | 4/10 | 6/10 | 7/10 | 7/10 |
| comparison | 6/7 | 4/7 | 5/7 | 6/7 | 7/7 |
| dialogue | 7/11 | 6/11 | 8/11 | 6/11 | 8/11 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | fail | fail | fail | pass | pass |
| Q02 | pass | fail | fail | pass | pass |
| Q03 | fail | fail | fail | pass | pass |
| Q04 | fail | fail | fail | pass | pass |
| Q06 | pass | fail | fail | pass | pass |
| Q07 | pass | pass | pass | pass | pass |
| Q08 | pass | pass | pass | pass | pass |
| Q09 | pass | pass | pass | pass | pass |
| Q10 | pass | fail | fail | pass | pass |
| Q11 | pass | pass | pass | fail | fail |
| Q12 | pass | pass | pass | pass | pass |
| Q13 | pass | fail | fail | pass | pass |
| Q14 | pass | fail | fail | pass | pass |
| Q15 | pass | pass | pass | pass | pass |
| Q16 | pass | fail | pass | pass | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | fail | fail | pass | fail | pass |
| Q19 | pass | fail | fail | fail | pass |
| Q20 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |

## Scoring Policy & Provenance

- Scorer version: `scorer_v3_1`
- Selected scoring policy: `with_specs_v3_1` (`amount_semantics_overrides.yaml`, scenario `cafe_01`)
- Metadata & hashes: `metadata.json`
