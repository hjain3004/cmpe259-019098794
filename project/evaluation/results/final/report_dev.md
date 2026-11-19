# Pooled Evaluation Report

Runs pooled: 4 across 2 scenario(s).

- Scenario `cafe_01` (repeats, 2 run(s)): 20261117-234352-cafe_01-claude-haiku-5-5, 20261118-164027-cafe_01-claude-haiku-5-5
- Scenario `plumbing_01` (repeats, 2 run(s)): 20261118-141745-plumbing_01-claude-haiku-5-5, 20261118-161549-plumbing_01-claude-haiku-5-5

## Turn and conversation success

| Scope | Config | Turn success | Conversation success | Parse rate |
| --- | --- | --- | --- | --- |
| cafe_01 | C0 | 35/56 (62%) | 26/42 (62%) | 53/56 (95%) |
| cafe_01 | C1 | 25/56 (45%) | 13/42 (31%) | 56/56 (100%) |
| cafe_01 | C2 | 29/56 (52%) | 16/42 (38%) | 56/56 (100%) |
| cafe_01 | C3 | 38/56 (68%) | 26/42 (62%) | 52/56 (93%) |
| cafe_01 | C4 | 41/56 (73%) | 29/42 (69%) | 56/56 (100%) |
| plumbing_01 | C0 | 47/80 (59%) | 33/60 (55%) | 74/80 (92%) |
| plumbing_01 | C1 | 29/80 (36%) | 22/60 (37%) | 78/80 (98%) |
| plumbing_01 | C2 | 42/80 (52%) | 28/60 (47%) | 80/80 (100%) |
| plumbing_01 | C3 | 46/80 (57%) | 31/60 (52%) | 78/80 (98%) |
| plumbing_01 | C4 | 44/80 (55%) | 29/60 (48%) | 79/80 (99%) |
| **Pooled** | **C0** | **82/136 (60%)** | **59/102 (58%)** | **127/136 (93%)** |
| **Pooled** | **C1** | **54/136 (40%)** | **35/102 (34%)** | **134/136 (99%)** |
| **Pooled** | **C2** | **71/136 (52%)** | **44/102 (43%)** | **136/136 (100%)** |
| **Pooled** | **C3** | **84/136 (62%)** | **57/102 (56%)** | **130/136 (96%)** |
| **Pooled** | **C4** | **85/136 (62%)** | **58/102 (57%)** | **135/136 (99%)** |

## Run-to-run spread (min–max turn success across repeats)

| Config | cafe_01 | plumbing_01 |
| --- | --- | --- |
| C0 | 57%–68% | 57%–60% |
| C1 | 43%–46% | 35%–38% |
| C2 | 50%–54% | 50%–55% |
| C3 | 68%–68% | 52%–62% |
| C4 | 71%–75% | 52%–57% |

## Error rates and grounding (pooled)

| Config | Unwarranted-warning rate | Over-abstention rate | Citation recall | Citation precision |
| --- | --- | --- | --- | --- |
| C0 | 28/106 (26%) | 1/92 (1%) | 0.998 | 0.427 |
| C1 | 29/106 (27%) | 27/92 (29%) | 0.604 | 0.303 |
| C2 | 32/106 (30%) | 18/92 (20%) | 0.757 | 0.405 |
| C3 | 24/106 (23%) | 1/92 (1%) | 0.869 | 0.617 |
| C4 | 29/106 (27%) | 1/92 (1%) | 0.842 | 0.603 |

## Per-question-type turn success (pooled)

| Label | C0 | C1 | C2 | C3 | C4 |
| --- | --- | --- | --- | --- | --- |
| lookup | 8/16 | 4/16 | 6/16 | 7/16 | 9/16 |
| aggregation | 22/38 | 12/38 | 14/38 | 25/38 | 22/38 |
| temporal | 17/34 | 10/34 | 13/34 | 21/34 | 22/34 |
| linking | 27/46 | 15/46 | 26/46 | 24/46 | 26/46 |
| comparison | 28/40 | 20/40 | 22/40 | 26/40 | 25/40 |
| dialogue | 30/54 | 22/54 | 28/54 | 32/54 | 32/54 |
| abstention | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |

## Paired statistics (pooled turns, 10000 bootstrap resamples, `(scenario, query_id)` clusters)

| Pair (A vs B) | Discordant (A:B) | Exact McNemar p | Diff (A - B) | 95% Bootstrap CI |
| --- | --- | --- | --- | --- |
| C0 vs C1 | 34:6 | 0.000 | +20.6% | [+9.4%, +32.3%] |
| C0 vs C2 | 22:11 | 0.080 | +8.1% | [-2.8%, +18.8%] |
| C0 vs C3 | 17:19 | 0.868 | -1.5% | [-11.5%, +8.9%] |
| C0 vs C4 | 15:18 | 0.728 | -2.2% | [-11.9%, +7.0%] |
| C1 vs C2 | 6:23 | 0.002 | -12.5% | [-20.5%, -5.0%] |
| C1 vs C3 | 12:42 | 0.000 | -22.1% | [-34.5%, -9.6%] |
| C1 vs C4 | 6:37 | 0.000 | -22.8% | [-33.3%, -12.3%] |
| C2 vs C3 | 13:26 | 0.053 | -9.6% | [-20.4%, +1.4%] |
| C2 vs C4 | 10:24 | 0.024 | -10.3% | [-19.7%, -1.4%] |
| C3 vs C4 | 9:10 | 1.000 | -0.7% | [-7.0%, +5.3%] |

### Power planning (observed median discordance rate 26.5%, alpha = 0.05, power = 80%)

| N turns | Minimum detectable difference |
| --- | --- |
| 60 | 19% |
| 90 | 16% |
| 120 | 14% |
