# Challenge Rescoring Reconciliation (`cafe_01`, `CH1`–`CH7`)

Historical challenge runs are preserved untouched. This report compares original saved `log.jsonl`, existing `<run>/rescored/log.jsonl` (where present), and `scorer_v3` using the exact same saved `raw_response` strings (zero model calls).

## Run `20261119-103951-cafe_01`
- Original path: `evaluation/results/challenge/20261119-103951-cafe_01`
- Model: `claude-haiku-5-5`, prompt: `answer_system_v2`, original commit: `4f23435`
- Original `log.jsonl`: **8/17**
- Prior `rescored/log.jsonl`: **14/17**
- Under `scorer_v3`: **14/17**

| Config | Query | Turn | Orig | Prior Rescored | `scorer_v3` | Key Differences |
| --- | --- | --- | --- | --- | --- | --- |
| C3 | CH1 | t0 | PASS | PASS | FAIL | orig_vals={'GP-221': True, '268.90 USD': True, 'NS-1062': True, '1073.25 USD': True, 'NS-1070': True, '389.60 USD': True, 'GP-228': True, '212.30': True, '512.30': True} vs v3_vals={'GP-221': True, '268.90 USD': False, 'NS-1062': True, '1073.25 USD': False, 'NS-1070': True, '389.60 USD': False, 'GP-228': True, '212.30 USD': False, '512.30 USD': False}; prior_vals={'GP-221': True, '268.90 USD': True, 'NS-1062': True, '1073.25 USD': True, 'NS-1070': True, '389.60 USD': True, 'GP-228': True, '212.30': True, '512.30': True} vs v3_vals={'GP-221': True, '268.90 USD': False, 'NS-1062': True, '1073.25 USD': False, 'NS-1070': True, '389.60 USD': False, 'GP-228': True, '212.30 USD': False, '512.30 USD': False} |
| C3 | CH1 | t1 | FAIL | PASS | PASS | orig_vals={'300.00': True, 'm03 OR paid in full': True, '212.30': True} vs v3_vals={'300.00 USD': True, 'm03 OR paid in full': True, '212.30 USD': True}; prior_vals={'300.00': True, 'm03 OR paid in full': True, '212.30': True} vs v3_vals={'300.00 USD': True, 'm03 OR paid in full': True, '212.30 USD': True}; must_not:['verified']->[] |
| C3 | CH2 | t1 | FAIL | PASS | PASS | must_not:['confirmed']->[] |
| C3 | CH2 | t2 | FAIL | PASS | PASS |  |
| C3 | CH3 | t1 | FAIL | PASS | PASS | ans_ok:False->True; orig_vals={} vs v3_vals={'481.20 USD': True, '781.20 USD': True}; prior_vals={'481.20': True, '781.20': True} vs v3_vals={'481.20 USD': True, '781.20 USD': True} |
| C3 | CH6 | t0 | FAIL | FAIL | PASS | orig_vals={'1750.00': False, '2026-09-18': True} vs v3_vals={'1750.00 USD': True, '2026-09-18': True}; prior_vals={'1750.00': False, '2026-09-18': True} vs v3_vals={'1750.00 USD': True, '2026-09-18': True} |
| C3 | CH7 | t0 | FAIL | PASS | PASS | orig_vals={'GP-221': True, 'NS-1062': True, '1342.15': False} vs v3_vals={} |
| C3 | CH7 | t1 | FAIL | PASS | PASS | orig_vals={'GP-221': True, 'NS-1062': True, '1342.15': False, 'Priya Shah': False} vs v3_vals={} |

## Run `20261119-110444-cafe_01`
- Original path: `evaluation/results/challenge/20261119-110444-cafe_01`
- Model: `claude-haiku-5-5`, prompt: `answer_system_v2`, original commit: `4f23435`
- Original `log.jsonl`: **12/17**
- Prior `rescored/log.jsonl`: **14/17**
- Under `scorer_v3`: **14/17**

| Config | Query | Turn | Orig | Prior Rescored | `scorer_v3` | Key Differences |
| --- | --- | --- | --- | --- | --- | --- |
| C3 | CH5 | t1 | FAIL | PASS | PASS | orig_vals={'1462.85': True, '847.45': False} vs v3_vals={'1462.85 USD': True} |
| C3 | CH6 | t0 | FAIL | PASS | PASS | orig_vals={'1750.00': False, '2026-09-18': True} vs v3_vals={'1750.00 USD': True, '2026-09-18': True} |

