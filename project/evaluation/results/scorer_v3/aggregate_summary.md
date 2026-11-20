# Aggregate `scorer_v3` Rescoring Summary (Separate Strata)

Scorer: `scorer_v3` | Git HEAD: `4f23435` | Working tree dirty: `True`

## Stratum: `historical_v1_core_dev`

Runs included: `evaluation/results/20261117-234352-cafe_01-claude-haiku-5-5` (baseline: `prior_rescored`), `evaluation/results/20261118-164027-cafe_01-claude-haiku-5-5` (baseline: `prior_rescored`), `evaluation/results/20261118-141745-plumbing_01-claude-haiku-5-5` (baseline: `prior_rescored`), `evaluation/results/20261118-161549-plumbing_01-claude-haiku-5-5` (baseline: `prior_rescored`)

| Config | Old Success | `scorer_v3` Success | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| C0 | 82/136 (60.3%) | 83/136 (61.0%) | +1 | 0 | 1 |
| C1 | 54/136 (39.7%) | 54/136 (39.7%) | +0 | 0 | 0 |
| C2 | 71/136 (52.2%) | 71/136 (52.2%) | +0 | 0 | 0 |
| C3 | 84/136 (61.8%) | 88/136 (64.7%) | +4 | 0 | 4 |
| C4 | 85/136 (62.5%) | 85/136 (62.5%) | +0 | 0 | 0 |

## Stratum: `v2_core_dev`

Runs included: `evaluation/results/20261118-223250-cafe_01-claude-haiku-5-5` (baseline: `orig`), `evaluation/results/20261118-224539-plumbing_01-claude-haiku-5-5` (baseline: `orig`)

| Config | Old Success | `scorer_v3` Success | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| C0 | 46/68 (67.6%) | 46/68 (67.6%) | +0 | 0 | 0 |
| C1 | 28/68 (41.2%) | 27/68 (39.7%) | -1 | 1 | 0 |
| C2 | 39/68 (57.4%) | 39/68 (57.4%) | +0 | 0 | 0 |
| C3 | 53/68 (77.9%) | 53/68 (77.9%) | +0 | 0 | 0 |
| C4 | 55/68 (80.9%) | 55/68 (80.9%) | +0 | 0 | 0 |

## Stratum: `v2_expanded_dev`

Runs included: `evaluation/results/20261118-231330-bakery_01-claude-haiku-5-5` (baseline: `orig`), `evaluation/results/20261118-232652-clinic_01-claude-haiku-5-5` (baseline: `orig`)

| Config | Old Success | `scorer_v3` Success | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| C0 | 37/53 (69.8%) | 37/53 (69.8%) | +0 | 0 | 0 |
| C1 | 29/53 (54.7%) | 27/53 (50.9%) | -2 | 2 | 0 |
| C2 | 27/53 (50.9%) | 27/53 (50.9%) | +0 | 0 | 0 |
| C3 | 30/53 (56.6%) | 30/53 (56.6%) | +0 | 0 | 0 |
| C4 | 31/53 (58.5%) | 31/53 (58.5%) | +0 | 0 | 0 |

## Stratum: `v2_scaling`

Runs included: `evaluation/results/20261119-001330-cafe_01_x4-claude-haiku-5-5` (baseline: `orig`), `evaluation/results/20261119-002636-cafe_01_x16-claude-haiku-5-5` (baseline: `orig`)

| Config | Old Success | `scorer_v3` Success | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| C0 | 43/56 (76.8%) | 43/56 (76.8%) | +0 | 0 | 0 |
| C1 | 20/56 (35.7%) | 20/56 (35.7%) | +0 | 0 | 0 |
| C2 | 13/56 (23.2%) | 13/56 (23.2%) | +0 | 0 | 0 |
| C3 | 45/56 (80.4%) | 45/56 (80.4%) | +0 | 0 | 0 |
| C4 | 43/56 (76.8%) | 43/56 (76.8%) | +0 | 0 | 0 |

## Stratum: `v2_held_out`

Runs included: `evaluation/results/20261119-010517-landscaping_01-claude-haiku-5-5` (baseline: `orig`)

| Config | Old Success | `scorer_v3` Success | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| C0 | 25/40 (62.5%) | 25/40 (62.5%) | +0 | 0 | 0 |
| C1 | 16/40 (40.0%) | 16/40 (40.0%) | +0 | 0 | 0 |
| C2 | 20/40 (50.0%) | 20/40 (50.0%) | +0 | 0 | 0 |
| C3 | 29/40 (72.5%) | 29/40 (72.5%) | +0 | 0 | 0 |
| C4 | 27/40 (67.5%) | 27/40 (67.5%) | +0 | 0 | 0 |

