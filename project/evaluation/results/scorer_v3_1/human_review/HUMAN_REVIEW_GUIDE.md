# Human Review Guide (`scorer_v3_1`)

## Files
- `blind_verdict_changes_and_policy_review.csv` (**8** rows): every turn where Comparison A, Comparison B, or sign-only policy review triggered.
- `blind_unchanged_sample.csv` (**48** rows): stratified sample of unchanged turns across all strata and pass/fail outcomes (seed `259`).
- Separate keys (`key_verdict_changes_and_policy_review.csv`, `key_unchanged_sample.csv`): keep closed until all blind labels are filled.

## Review Rubric
1. Judge `displayed_reply` against `turn_text` and the bundle records (not against automated verdicts).
2. Enter `PASS` or `FAIL` in `human_verdict`.
3. In `human_notes`, note any policy-sensitive issue:
   - **Bank outflow sign:** whether a negative statement debit (`-300.00 USD`, `-550.00 USD`, `-1,750.00 USD`) is an accurate answer to a payment/transaction question.
   - **Scoped currency:** whether a header declaration (`All amounts in USD`, `(all USD)`) unambiguously governs subsequent bare amounts.
   - **Entity-value binding / contradictory prose:** whether the right number was attached to the wrong invoice or contradicted elsewhere in the reply.
   - **Reply-type boundary:** whether `CLARIFY` vs `ABSTAIN` or `ANSWER` vs `WARN` was defensible.

## Remaining Policy-Sensitive Cases Routed for Review
- `v2_core_dev` / `cafe_01` `Q17 t2` (sign-only debit keys: `payment`; strict=`False`, with `specs_v3_1`=`True`)
- `v2_expanded_dev` / `clinic_01` `D214 t0` (sign-only debit keys: `amount`; strict=`False`, with `specs_v3_1`=`True`)
- `v2_expanded_dev` / `clinic_01` `D214 t1` (sign-only debit keys: `total`; strict=`False`, with `specs_v3_1`=`True`)
