# Scoring Integrity Revision (`scorer_v3_1`) & Evaluation Policy Specification

**Scorer version:** `scorer_v3_1` (`code/src/cashbooks/scoring.py`)  
**Versioned overrides:** `evaluation/specs_v3_1/amount_semantics_overrides.yaml` (`evaluation/specs_v3_1/manifest.json`)  
**Outputs:** `evaluation/results/scorer_v3_1/` (prior `evaluation/results/scorer_v3/` and all historical runs preserved untouched)

---

## 1. Amount Semantics Taxonomy & Explicit Specification Mechanism

`scorer_v3_1` separates three distinct numeric/money semantics instead of inferring semantics from whichever model reply happens to pass:

| Semantics | Default For | Sign Behavior | Currency Behavior | Example |
| --- | --- | --- | --- | --- |
| `signed_money` | `"<amount> <CUR>"` (default) | **Strict:** `+42.00 != -42.00` | Must be established (explicit tag, unambiguous symbol, clean scoped declaration, or unconflicted USD `$`) | `"42.00 USD"`, `"-42.00 USD"` |
| `txn_magnitude` | Explicitly declared only (`{"kind": "txn_magnitude", "value": "..."}`) | Accepts positive outflow magnitude (`$550.00 USD`) **and** negative statement representation (`-550.00 USD`) | Identical strict currency & numeric boundary rules (rejects `-550.00 EUR`, `-1,550.00 USD`, bare `-550.00`) | Bank-outflow queries (`Q17 t2`, `D214 t0/t1`, `CH6 t0`) |
| `non_money_number` | Bare numeric strings (`"12"`, `"6611"`, `"300.00"`) | **Strict** by default (`12 != -12`); supports explicit `txn_magnitude` if declared | No currency required; strict numeric boundaries + valid thousands commas | Counts, last-4 digits, bare amounts |

### Recommended Mechanism for New Evaluation Specifications
New or revised evaluation specifications declare transaction-magnitude semantics explicitly via a typed mapping rather than altering historical gold:
```yaml
values:
  amount:
    kind: txn_magnitude
    value: "550.00 USD"
```
Historical gold files (`data/dev/*/gold.yaml`, `data/test/landscaping_01/gold.yaml`, `evaluation/challenge/cafe_challenge_gold.yaml`) remain untouched. Versioned overrides for bank-outflow questions live separately under `evaluation/specs_v3_1/amount_semantics_overrides.yaml` with a change manifest (`evaluation/specs_v3_1/manifest.json`).

### Routing Unresolved Legacy Sign Cases to Policy Review
When an unannotated positive amount in historical gold fails strict default `signed_money` matching **solely** because the reply wrote a negative statement debit with the exact magnitude and valid currency (`check_sign_only_mismatch`), `scorer_v3_1` does **not** silently pass it and `rescore_v3_1.py` does **not** treat it as a proven model failure: it flags `policy_review:sign_only_debit` and routes the turn into the blinded human-review packet.

---

## 2. Explicit Scoped Currency Rules

An explicit scoped currency declaration (e.g., `"All amounts in USD"`, `"(all USD)"`, `"All balances are in EUR:"`, `"Currency: GBP"`) establishes currency for **subsequent** bare amounts (`m.start() >= scope_start`), subject to strict anti-ambiguity guards:
1. **No retroactive scope:** Bare amounts appearing *before* the declaration are rejected.
2. **Compound / ambiguous declarations rejected:** `"All amounts in USD or EUR"`, `"USD and EUR"`, `"USD/EUR"`, `"Currency: USD, EUR"` establish no scope.
3. **Contradictory declarations rejected:** Two declarations naming different currencies in the same reply invalidate scope.
4. **Scope contamination rejected:** If a different currency (ISO code or incompatible symbol) appears after the declaration, scope is invalidated so bare amounts never silently pass.
5. **Explicit mention-level tags & structured conflicts win:** `"All amounts in USD. Total is 42.00 EUR."` and conflicting `calculation.result` currencies always reject `42.00 USD`.
6. **Numeric boundaries and strict sign rules still apply inside scope.**

---

## 3. Documented Updates to Two Legacy Assertions in `code/tests/test_challenge.py`

1. `test_section_exclude_recipient_email_and_or_values` (`test_challenge.py:66, 91`): The test exercises `section_exclude` and OR-value checks on `CH1`, where `cafe_challenge_gold.yaml` specifies `"212.30 USD"`, `"512.30 USD"`, and `"300.00 USD"`. Its mock answers previously omitted `$`/`USD` (relying on the prior currency-ignoring scorer). Updated the mock answers to include explicit `$... USD` currency tags.
2. `test_money_values_have_currency_and_cafe_ch5_accepts_open_total` (`test_challenge.py:553–566`): Previously asserted that negative `"-1,750.00 USD"` matched historical positive `"1750.00 USD"` under default matching. Updated to assert the intended two-layer policy:
   - Under historical gold (`"1750.00 USD"`, default strict `signed_money`), positive `"$1,750.00"` passes while `"-1,750.00 USD"` fails and triggers `check_sign_only_mismatch`.
   - Under explicit `{"kind": "txn_magnitude", "value": "1750.00 USD"}`, both `"-1,750.00 USD"` and `"$1,750.00"` pass.

---

## 4. Separated Comparisons A & B (`evaluation/results/scorer_v3_1/`)

### Comparison A — Old vs. New Scorer with Identical Postprocessing (Pure Scorer-Only)
Both `legacy_v2_scorer` and `scorer_v3_1` score the **exact same `AssistantResponse`** produced by the current `postprocess()`. Full tables in `evaluation/results/scorer_v3_1/comparison_a_scorer_only.md`.

- `historical_v1_core_dev`: **0** scorer-only changes across all 680 config-turns (`C0`–`C4`).
- `v2_core_dev`: **1** strict change (`C1`: `28/68 → 27/68`, `cafe_01 Q17 t2` routed to policy review; `28/68` with `specs_v3_1`). `C0`, `C2`, `C3`, `C4`: **0** changes.
- `v2_expanded_dev`: **2** strict changes (`C1`: `29/53 → 27/53`, `clinic_01 D214 t0` & `t1` routed to policy review; `29/53` with `specs_v3_1`). `C0`, `C2`, `C3`, `C4`: **0** changes.
- `v2_scaling` (`cafe_01_x4`, `cafe_01_x16`): **0** changes across all 280 config-turns.
- `v2_held_out` (`data/test/landscaping_01`): **0** changes across all 200 config-turns (`C0` 25/40, `C1` 16/40, `C2` 20/40, `C3` 29/40, `C4` 27/40).

### Comparison B — Historical Recorded Results vs. Current Pipeline Reprocessing
Compares historical recorded logs directly against current `postprocess()` + `scorer_v3_1`. **Not a scorer-only comparison:** exact historical `v1` postprocessing cannot be reconstructed from the current working tree alone (`postprocess.py` evolved across commits with `default_as_of`, unknown-key dropping, `ABSTAIN`/`CLARIFY` calculation dropping, and `result` normalization). Full tables in `evaluation/results/scorer_v3_1/comparison_b_historical_vs_pipeline.md`.

- `historical_v1_core_dev`: **+5** net changes (`C0` +1, `C3` +4) — **100% attributed to `postprocess.py` parse recovery**, **0** attributed to scorer rules.
- `v2` strata (`v2_core_dev`, `v2_expanded_dev`, `v2_scaling`, `v2_held_out`): **0** parse-recovery changes; the only **3** differences are the `C1` sign-only debit cases above.

### Challenge Runs (`evaluation/results/scorer_v3_1/challenge_summary.md`)
- `20261119-103951-cafe_01`: `8/17` orig → `14/17` prior rescored → **`15/17`** under `scorer_v3_1` (`CH1 t0` passes via its explicit `"(all USD)"` scoped currency declaration; `CH6 t0` passes via updated `'1750.00 USD'` gold).
- `20261119-110444-cafe_01`: `12/17` orig → `14/17` prior rescored → **`14/17`** under `scorer_v3_1` (`CH5 t1` and `CH6 t0` changed from gold updates, not model changes).

---

## 5. Human Review Packet & Remaining Policy-Sensitive Cases

Generated under `evaluation/results/scorer_v3_1/human_review/` (all human labels left blank, configuration and automated verdicts hidden in blind CSVs, keys stored separately):
- `blind_verdict_changes_and_policy_review.csv` (**8** rows) + `key_verdict_changes_and_policy_review.csv`
- `blind_unchanged_sample.csv` (**48** rows, stratified across all strata and pass/fail, seed `259`) + `key_unchanged_sample.csv`
- `HUMAN_REVIEW_GUIDE.md`

**Remaining policy-sensitive cases routed for human review (all 3 are `C1` bank-debit sign-only cases):**
1. `v2_core_dev` / `cafe_01` `Q17 t2` (`payment: "300.00"` vs `"-300.00 USD"` bank debit)
2. `v2_expanded_dev` / `clinic_01` `D214 t0` (`amount: "550.00 USD"` vs `"-550.00 USD"` bank debit)
3. `v2_expanded_dev` / `clinic_01` `D214 t1` (`total: "550.00 USD"` vs `"-550.00 USD"` bank debit)

All SHA-256 hashes of `scoring.py`, `postprocess.py`, `rescore_v3_1.py`, `specs_v3_1`, and every gold and query specification file are recorded in `evaluation/results/scorer_v3_1/manifest.json` and per-run `metadata.json` files.
