# Run 20261118-223250-cafe_01-claude-haiku-5-5 (scorer_v3_1:strict_historical)

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `7a5dd10`, scenario `cafe_01`, 21 conversations, 28 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 20/28 (71%) | 14/21 | 82% | 94% | 27/28 | 6.85 | 7872 |
| C1 | 13/28 (46%) | 8/21 | 64% | 77% | 27/28 | 5.86 | 5004 |
| C2 | 15/28 (54%) | 10/21 | 68% | 77% | 28/28 | 5.76 | 4709 |
| C3 | 22/28 (79%) | 17/21 | 82% | 91% | 27/28 | 4.78 | 11019 |
| C4 | 22/28 (79%) | 16/21 | 82% | 97% | 25/28 | 4.71 | 11501 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 2/21 (10%) | 0/18 (0%) |
| C1 | 1/21 (5%) | 6/18 (33%) |
| C2 | 3/21 (14%) | 3/18 (17%) |
| C3 | 0/21 (0%) | 0/18 (0%) |
| C4 | 0/21 (0%) | 0/18 (0%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.462 | 4.04 | 66 | 131 | 82% |
| C1 | 0.636 | 0.310 | 3.59 | 75 | 121 | 89% |
| C2 | 0.705 | 0.363 | 3.93 | 88 | 120 | 89% |
| C3 | 0.810 | 0.644 | 3.44 | 62 | 95 | 93% |
| C4 | 0.900 | 0.685 | 3.56 | 61 | 95 | 100% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 2/4 | 1/4 | 2/4 | 4/4 | 4/4 |
| aggregation | 6/8 | 2/8 | 4/8 | 7/8 | 6/8 |
| temporal | 4/7 | 1/7 | 3/7 | 7/7 | 6/7 |
| linking | 7/10 | 4/10 | 5/10 | 6/10 | 7/10 |
| comparison | 6/7 | 4/7 | 3/7 | 6/7 | 7/7 |
| dialogue | 8/11 | 5/11 | 5/11 | 7/11 | 7/11 |
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
| Q13 | fail | fail | fail | fail | pass |
| Q14 | fail | fail | pass | pass | pass |
| Q15 | pass | pass | pass | pass | fail |
| Q16 | pass | fail | pass | pass | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | pass | fail | fail | pass | pass |
| Q19 | pass | fail | fail | pass | fail |
| Q20 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |

## Scoring Policy & Provenance

- Scorer version: `scorer_v3_1`
- Selected primary policy: `strict_historical`
- Metadata & hashes: `metadata.json`
