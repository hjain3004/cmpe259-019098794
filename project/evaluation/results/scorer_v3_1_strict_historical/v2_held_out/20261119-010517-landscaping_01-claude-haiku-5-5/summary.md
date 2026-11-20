# Run 20261119-010517-landscaping_01-claude-haiku-5-5 (scorer_v3_1:strict_historical)

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `7a5dd10`, scenario `landscaping_01`, 30 conversations, 40 scored turns.

| Config | Turn success | Conversation success | Answer type | Exact values | Parsed | Median latency (s) | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | 25/40 (62%) | 17/30 | 78% | 85% | 38/40 | 6.64 | 9470 |
| C1 | 16/40 (40%) | 12/30 | 68% | 67% | 39/40 | 5.92 | 5136 |
| C2 | 20/40 (50%) | 13/30 | 65% | 78% | 39/40 | 5.32 | 4862 |
| C3 | 29/40 (72%) | 21/30 | 85% | 82% | 39/40 | 5.29 | 12900 |
| C4 | 27/40 (68%) | 20/30 | 82% | 80% | 39/40 | 5.26 | 12684 |

## Error rates

| Config | Unwarranted-warning rate | Over-abstention rate |
| --- | --- | --- |
| C0 | 0/32 (0%) | 2/28 (7%) |
| C1 | 1/32 (3%) | 7/28 (25%) |
| C2 | 3/32 (9%) | 6/28 (21%) |
| C3 | 0/32 (0%) | 1/28 (4%) |
| C4 | 0/32 (0%) | 1/28 (4%) |

## Grounding and usability

| Config | Mean recall | Mean precision | Mean citations | Median words | P90 words | Under 120 words |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | 1.000 | 0.541 | 4.42 | 78 | 124 | 87% |
| C1 | 0.571 | 0.366 | 3.46 | 93 | 118 | 95% |
| C2 | 0.672 | 0.473 | 3.54 | 82 | 129 | 90% |
| C3 | 0.838 | 0.611 | 4.00 | 80 | 114 | 92% |
| C4 | 0.747 | 0.552 | 3.74 | 76 | 108 | 97% |

## Per-question-type turn success

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 4/4 | 1/4 | 2/4 | 2/4 | 3/4 |
| aggregation | 5/11 | 3/11 | 5/11 | 7/11 | 5/11 |
| temporal | 5/10 | 1/10 | 4/10 | 5/10 | 5/10 |
| linking | 8/13 | 5/13 | 7/13 | 11/13 | 10/13 |
| comparison | 8/13 | 7/13 | 6/13 | 11/13 | 11/13 |
| dialogue | 10/16 | 5/16 | 7/16 | 10/16 | 9/16 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Conversation success

| Conversation | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| Q01 | pass | fail | fail | fail | fail |
| Q02 | fail | fail | fail | fail | fail |
| Q03 | pass | fail | fail | fail | pass |
| Q04 | fail | fail | fail | pass | pass |
| Q05 | pass | pass | pass | pass | pass |
| Q06 | pass | pass | pass | pass | pass |
| Q07 | pass | fail | fail | pass | pass |
| Q08 | pass | pass | pass | pass | pass |
| Q09 | pass | pass | pass | pass | pass |
| Q10 | pass | fail | fail | pass | pass |
| Q11 | pass | pass | pass | pass | fail |
| Q12 | fail | pass | pass | pass | pass |
| Q13 | fail | fail | fail | pass | pass |
| Q14 | fail | fail | fail | fail | fail |
| Q15 | pass | pass | pass | pass | fail |
| Q16 | pass | fail | pass | pass | pass |
| Q17 | fail | fail | fail | fail | fail |
| Q18 | pass | pass | fail | pass | pass |
| Q19 | fail | fail | fail | fail | fail |
| Q20 | fail | fail | fail | fail | fail |
| Q21 | pass | fail | fail | pass | pass |
| Q22 | fail | fail | fail | fail | fail |
| Q23 | fail | fail | pass | pass | pass |
| Q24 | pass | pass | pass | pass | pass |
| Q25 | fail | fail | fail | pass | pass |
| Q26 | pass | pass | pass | pass | pass |
| Q27 | fail | fail | fail | pass | pass |
| Q28 | fail | fail | fail | fail | fail |
| Q29 | pass | pass | pass | pass | pass |
| Q30 | pass | pass | pass | pass | pass |

## Scoring Policy & Provenance

- Scorer version: `scorer_v3_1`
- Selected primary policy: `strict_historical`
- Metadata & hashes: `metadata.json`
