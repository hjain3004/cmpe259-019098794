# Per-Turn Verdict Changes Under `scorer_v3`

Total verdict-changing turns across all rescored strata: **10**.

| Stratum | Run | Config | Query | Turn | Baseline | Old | New | Cause | Changed Values |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| historical_v1_core_dev | `20261117-234352-cafe_01-claude-haiku-5-5` | C3 | Q01 | t0 | prior_rescored | FAIL | PASS | `parse_changed:False->True; answerability_ok:False->True; scorer_v3_money_rule:balance; scorer_v3_value_rule:bill; scorer_v3_value_rule:due; evidence_recall_changed:None->1.0` | `balance=1073.25 USD(None->True); bill=NS-1062(None->True); due=2026-10-01(None->True)` |
| historical_v1_core_dev | `20261118-164027-cafe_01-claude-haiku-5-5` | C0 | Q20 | t0 | prior_rescored | FAIL | PASS | `parse_changed:False->True; answerability_ok:False->True` | `` |
| historical_v1_core_dev | `20261118-164027-cafe_01-claude-haiku-5-5` | C3 | Q11 | t0 | prior_rescored | FAIL | PASS | `parse_changed:False->True; answerability_ok:False->True; scorer_v3_value_rule:answer; evidence_recall_changed:None->1.0` | `answer=yes(None->True)` |
| historical_v1_core_dev | `20261118-164027-cafe_01-claude-haiku-5-5` | C3 | Q18 | t2 | prior_rescored | FAIL | PASS | `parse_changed:False->True; answerability_ok:False->True; scorer_v3_value_rule:last4; evidence_recall_changed:None->1.0` | `last4=4417(None->True)` |
| historical_v1_core_dev | `20261118-161549-plumbing_01-claude-haiku-5-5` | C3 | Q27 | t0 | prior_rescored | FAIL | PASS | `parse_changed:False->True; answerability_ok:False->True; scorer_v3_value_rule:alias; scorer_v3_value_rule:first; scorer_v3_value_rule:second; evidence_recall_changed:None->0.6666666666666666` | `alias=Crestline Flow Systems LLC(None->True); first=PL-314(None->True); second=CP-445(None->True)` |
| v2_core_dev | `20261118-223250-cafe_01-claude-haiku-5-5` | C1 | Q17 | t2 | orig | PASS | FAIL | `scorer_v3_value_rule:payment` | `payment=300.00(True->False)` |
| v2_expanded_dev | `20261118-232652-clinic_01-claude-haiku-5-5` | C1 | D214 | t0 | orig | PASS | FAIL | `scorer_v3_money_rule:amount` | `amount=550.00 USD(True->False)` |
| v2_expanded_dev | `20261118-232652-clinic_01-claude-haiku-5-5` | C1 | D214 | t1 | orig | PASS | FAIL | `scorer_v3_money_rule:total` | `total=550.00 USD(True->False)` |
| challenge_cafe | `20261119-103951-cafe_01` | C3 | CH1 | t0 | prior_rescored | PASS | FAIL | `challenge_scorer_v3_money_or_sign_rule` | `1073.25 USD(True->False); 212.30(True->None); 212.30 USD(None->False); 268.90 USD(True->False); 389.60 USD(True->False); 512.30(True->None); 512.30 USD(None->False)` |
| challenge_cafe | `20261119-103951-cafe_01` | C3 | CH6 | t0 | prior_rescored | FAIL | PASS | `challenge_scorer_v3_money_or_sign_rule` | `1750.00(False->None); 1750.00 USD(None->True)` |
