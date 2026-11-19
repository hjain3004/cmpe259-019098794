# Paired Statistics (20261118-231330-bakery_01-claude-haiku-5-5)

Runs: 2; bootstrap resamples: 10000 (seed 259, `(scenario, query_id)` clusters).

- Scenario `bakery_01` (single run, 1 run(s)): 20261118-231330-bakery_01-claude-haiku-5-5
- Scenario `clinic_01` (single run, 1 run(s)): 20261118-232652-clinic_01-claude-haiku-5-5

| Pair (A vs B) | Discordant (A:B) | Exact McNemar p | Diff (A - B) | 95% Bootstrap CI |
| --- | --- | --- | --- | --- |
| C0 vs C1 | 12:4 | 0.077 | +15.1% | [+0.0%, +32.0%] |
| C0 vs C2 | 13:3 | 0.021 | +18.9% | [+3.9%, +35.4%] |
| C0 vs C3 | 13:6 | 0.167 | +13.2% | [-1.9%, +28.3%] |
| C0 vs C4 | 12:6 | 0.238 | +11.3% | [-2.1%, +25.4%] |
| C1 vs C2 | 7:5 | 0.774 | +3.8% | [-9.6%, +16.4%] |
| C1 vs C3 | 12:13 | 1.000 | -1.9% | [-20.4%, +15.7%] |
| C1 vs C4 | 12:14 | 0.845 | -3.8% | [-24.0%, +14.5%] |
| C2 vs C3 | 12:15 | 0.701 | -5.7% | [-23.9%, +12.2%] |
| C2 vs C4 | 12:16 | 0.572 | -7.5% | [-26.9%, +10.3%] |
| C3 vs C4 | 2:3 | 1.000 | -1.9% | [-10.4%, +6.0%] |
