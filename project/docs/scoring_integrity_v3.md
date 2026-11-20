# Scoring Integrity Audit & `scorer_v3` Specification

**Scorer version:** `scorer_v3` (`code/src/cashbooks/scoring.py`)  
**Scope:** Narrow correctness repair of deterministic numeric and money value matching, offline rescoring of saved runs into `evaluation/results/scorer_v3/`, challenge-history reconciliation, and blinded human-review packet generation.  

---

## 1. Definite Implementation Defects in Prior Scorer (`v1`/`v2`)

Inspecting `code/src/cashbooks/scoring.py` (`money_variants`, `check_value`) identified four definite implementation defects, separate from broader metric-design limitations:

1. **Unbounded substring matching for money values (`scoring.py:139`):**
   - Prior logic checked `any(v in text for v in money_variants(amount))`, where `money_variants(Decimal("42.00"))` produced `{"42.00", "$42.00", "$42"}`.
   - `"42.00" in "The total is 142.00 EUR."` returned `True`.
   - `"$42" in "The total is $42.50."` and `"$42" in "$420"` returned `True`.
   - `"42.00" in "1,042.00"` returned `True`.
2. **Currency completely unenforced in prose fallback (`scoring.py:136–139`):**
   - `check_value("42.00 USD", resp)` checked `calc.currency == "USD"` only on `resp.calculation.result`, then fell through to `money_variants(amount)` which discarded `m.group(2)` (the expected ISO currency code).
   - As a result, `"The total is 142.00 EUR."`, `"The total is 42.00 EUR."`, and even a structured `calculation.result = Money(amount=Decimal("42.00"), currency="EUR")` with `"42.00"` in prose or `calculation.steps` all returned `True` for `"42.00 USD"`.
3. **Positive vs. negative signs collapsed (`scoring.py:68`):**
   - `money_variants` took `a = abs(amount)`, erasing sign information.
   - `"-42.00 USD"` matched positive `"42.00 USD"`, and `"42.00 USD"` matched negative `"-42.00 USD"` or `"-$42.00"`.
4. **Bare-number boundary & comma-formatting defects (`scoring.py:144–145`):**
   - `re.search(rf"(?<![\d.]){re.escape(exp)}(?![\d])", text)` allowed bare `"42"` to match `"42.50"` (decimal point not excluded on right), `"1,042"` (comma not excluded on left), and `"-42"` (attached unary minus not excluded on left), while failing to match valid thousands-grouped formatting such as `"1,250.00"` for expected `"1250.00"`.

---

## 2. Frozen `scorer_v3` Money & Numeric Matching Rules

These rules are frozen from constructed test cases and development conventions before rescoring any saved evaluation outputs, and apply identically across `C0`–`C4`.

### Context Available to `check_value(expected, resp)`
`check_value` receives only:
- `expected: str` (for money: `^(-?\d+(?:\.\d{1,2})?)\s+([A-Z]{3})$`, e.g. `42.00 USD`, `-1750.00 USD`, `700.00 EUR`)
- `resp: AssistantResponse` (`answer`, `clarifying_question`, `next_step`, `risk_indicators`, `calculation.steps`, and optional structured `calculation.result: Money(amount, currency)`).

`check_value` does **not** receive `ledger.json`, bundle defaults, or hidden tool payloads.

### Rule A — Structured `calculation.result` Check
1. If `resp.calculation` is present and `resp.calculation.result.amount == expected_amount` and `resp.calculation.result.currency == expected_currency`, return `True`.
2. If `resp.calculation` is present and `resp.calculation.result.amount == expected_amount` with a **different** currency (`calc.currency != expected_currency`), this is a **conflicting structured currency** for that amount: it does not pass on `calculation.result`, and bare `$` in prose cannot override it (only an explicitly currency-tagged prose mention of `expected_currency` can match, to allow genuine multi-currency replies).

### Rule B — Numeric Boundaries, Sign, Commas, and Equivalent Decimal Formatting
In prose fallback over `_text(resp)`, each candidate money mention must satisfy:
1. **Strict numeric boundaries:**
   - Magnitude matches either plain digits (`\d+(?:\.\d{1,2})?`) or valid 3-digit comma-grouped digits (`\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?`).
   - Left boundary forbids preceding digits, `.`, or `,` (`(?<![\d.,])`), so `42.00` never matches inside `142.00`, `1,042.00`, or `0.42.00`.
   - Right boundary forbids trailing digits, `.\d`, or `,\d` (`(?![\d])(?!\.\d)(?!,\d)`), so `42` never matches inside `42.50`, `420`, or `42,000`, and `42.00` never matches inside `42.005`, while sentence-ending punctuation (`$42.00.`) remains valid.
2. **Exact `Decimal` equivalence:**
   - Commas are stripped and parsed as `Decimal`. Equivalent integer/decimal representations (`42`, `42.0`, `42.00`; `1073.25`, `1,073.25`) compare equal; non-equal values (`42.50`, `142.00`) fail.
3. **Sign enforcement:**
   - Directly attached `-` or Unicode minus `−` (U+2212) before the currency symbol (`-$42.00`, `-€42.00`) or directly before digits (`$-42.00`, `-42.00 USD`, `USD -42.00`) marks a negative amount.
   - Whitespace-separated hyphens (e.g., `GP-221 - $42.00` or subtraction steps `"- 45.00 credit"`) are treated as separators/operators, not unary negative signs. Parenthetical positive mentions (`GP-221 ($42.00 USD)`) remain positive.
   - Expected `amount > 0` requires a non-negative mention; expected `amount < 0` requires a negative mention; expected `amount == 0` matches `0` / `0.00`.

### Rule C — How Currency Is Established in Prose
Every candidate money mention in prose must establish currency; a bare number with no currency symbol and no attached ISO code (e.g., `"The total is 42.00."`) does **not** match `"42.00 USD"` or `"42.00 EUR"`.

1. **Explicit ISO code attached to the mention** (prefix such as `USD 42.00`, `USD $42.00`, `EUR €42.00`, `CAD 42.00`, or suffix such as `42.00 USD`, `$42.00 USD`, `42.00 EUR`, `$42.00 CAD`):
   - Recognized from a curated ISO-4217 currency set plus `expected_currency` itself (preventing English 3-letter words like `DUE` or `TAX` from being misread as currency codes).
   - Qualified dollar prefixes (`US$` → `USD`, `CA$`/`C$` → `CAD`, `AU$`/`A$` → `AUD`, `NZ$` → `NZD`, `HK$` → `HKD`, `S$`/`SG$` → `SGD`, `MX$` → `MXN`) are treated as explicit currency tags.
   - If both prefix and suffix tags are present and disagree (e.g. `EUR 42.00 USD`), the mention is rejected.
   - Otherwise the mention matches if and only if its explicit currency equals `expected_currency`.
2. **Unambiguous single-currency symbols** (when no explicit ISO tag is attached):
   - `€` establishes `EUR`; `£` establishes `GBP`.
   - Ambiguous symbols such as `¥` (`JPY`/`CNY`) require an explicit ISO code.
3. **Bare `$` symbol (no explicit ISO code or qualified prefix):**
   - Bare `$` is **never** assumed to mean `USD` unconditionally:
     - Rejected for all non-`USD` expected currencies (`EUR`, `CAD`, `AUD`, `NZD`, `GBP`, etc.).
     - Rejected even for expected `USD` if any other dollar-denominated currency (`CAD`, `AUD`, `NZD`, `HKD`, `SGD`, `MXN`) is mentioned anywhere in `resp`, or if `resp.calculation.result` conflicts on currency for the same amount (`calc.amount == expected_amount and calc.currency != "USD"`).
   - Accepted for expected `USD` **only** within CashBooks Assist's `Currency = Literal["USD", "EUR"]` contract scope when no other dollar currency appears in the response and no structured calculation currency conflicts.

### Rule D — Bare Numeric Values (Non-Money)
For bare numeric gold values matching `^(-?\d+(?:\.\d+)?)$` (e.g., `"12"`, `"300.00"`, `"1250.00"`, `"6611"`):
- Enforces left boundary excluding digits, `.`, `,`, letters, and attached unary minus (for positive values; negative values require attached `-`/`−`), while still allowing masked account prefixes like `****6611`.
- Enforces right boundary excluding digits and `.\d`.
- Accepts valid 3-digit comma-grouped formatting for magnitudes $\ge 1000$ (e.g. `"1,250.00"` matches `"1250.00"`).

---

## 3. Broader Scoring Limitations (Audited, Not Rewritten)

The narrow fix above repairs definite string-matching bugs without altering metric semantics. The following structural limitations of deterministic scoring remain and are **not** solved by `scorer_v3`:

1. **Entity–value binding is not verified:** `check_value` checks that each expected value appears *somewhere* in `_text(resp)` (which concatenates `answer`, `clarifying_question`, `next_step`, `risk_indicators`, and `calculation.steps`). If a reply mentions two invoices and swaps their amounts or due dates, `check_value` can still pass.
2. **Contradictory prose can pass:** Because `check_value` is existential (any valid matching occurrence passes), a response that states `"$42.00 USD (or maybe $99.00 USD)"` or states the right number in `calculation.steps` while giving a wrong conclusion in `answer` can pass deterministic value checks unless caught by `must_not`.
3. **Partial evidence recall gates turn success (`recall > 0`):** `score_turn` requires `recall > 0` whenever `gold_evidence` is non-empty, rather than `recall == 1.0`. A turn citing 1 of 3 required documents still passes `success`, though mean citation recall and precision are tracked separately.
4. **Strict 4-way reply-type labels (`ANSWER` / `CLARIFY` / `ABSTAIN` / `WARN`):** Standard evaluation requires exact equality (`resp.answerability == expected`), which can penalize defensible boundary choices (e.g., `CLARIFY` vs. `ABSTAIN` on underspecified or ambiguous turns, or `WARN` vs. `ANSWER` when a vendor message contradicts bank records).
5. **Deterministic matching does not verify semantic correctness:** Passing `scorer_v3` verifies structured contract compliance, bounded numeric/currency/date/status presence, document-level citation overlap, and `must_not` avoidance—not full reasoning validity. Independent human review remains necessary.

*(Rescoring results, per-turn change report, challenge history analysis, and blinded human-review packet manifest are appended below after freezing `scorer_v3` and running `evaluation/rescore_v3.py`.)*

---

## 4. Offline Rescoring Results (`evaluation/results/scorer_v3/`)

After freezing `scorer_v3` and verifying all 36 tests in `test_scoring_integrity_v3.py`, `test_scoring_and_stats.py`, `test_pipeline.py`, and `test_plumbing_bundle.py`, `evaluation/rescore_v3.py` rescored **1,799** scored turns offline across all available strata (`git HEAD: 4f23435`, working tree dirty due to concurrent work outside this assignment). All historical runs, logs, summaries, and existing `rescored/` directories remain untouched.

### Aggregate Changes per Stratum & Configuration (Never Pooled Across Strata)

#### 4.1 Historical `v1` Core Development (`cafe_01` ×2, `plumbing_01` ×2; baseline: prior `rescored/`)

| Config | Prior `rescored/` | `scorer_v3` | Delta | Pass→Fail | Fail→Pass | Cause |
| --- | --- | --- | --- | --- | --- | --- |
| `C0` | 82/136 (60.3%) | 83/136 (61.0%) | +1 | 0 | 1 | `postprocess.py` parse recovery (`Q20 t0`), not `scorer_v3` money rules |
| `C1` | 54/136 (39.7%) | 54/136 (39.7%) | 0 | 0 | 0 | — |
| `C2` | 71/136 (52.2%) | 71/136 (52.2%) | 0 | 0 | 0 | — |
| `C3` | 84/136 (61.8%) | 88/136 (64.7%) | +4 | 0 | 4 | `postprocess.py` parse recovery (`Q01`, `Q11`, `Q18 t2`, `Q27`), not `scorer_v3` money rules |
| `C4` | 85/136 (62.5%) | 85/136 (62.5%) | 0 | 0 | 0 | — |

#### 4.2 Updated `v2` Core Development (`cafe_01` + `plumbing_01`; baseline: `orig`)

| Config | Original `v2` | `scorer_v3` | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| `C0` | 46/68 (67.6%) | 46/68 (67.6%) | 0 | 0 | 0 |
| `C1` | 28/68 (41.2%) | 27/68 (39.7%) | -1 | 1 | 0 |
| `C2` | 39/68 (57.4%) | 39/68 (57.4%) | 0 | 0 | 0 |
| `C3` | 53/68 (77.9%) | 53/68 (77.9%) | 0 | 0 | 0 |
| `C4` | 55/68 (80.9%) | 55/68 (80.9%) | 0 | 0 | 0 |

#### 4.3 Expanded `v2` Development (`bakery_01` + `clinic_01`; baseline: `orig`)

| Config | Original `v2` | `scorer_v3` | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| `C0` | 37/53 (69.8%) | 37/53 (69.8%) | 0 | 0 | 0 |
| `C1` | 29/53 (54.7%) | 27/53 (50.9%) | -2 | 2 | 0 |
| `C2` | 27/53 (50.9%) | 27/53 (50.9%) | 0 | 0 | 0 |
| `C3` | 30/53 (56.6%) | 30/53 (56.6%) | 0 | 0 | 0 |
| `C4` | 31/53 (58.5%) | 31/53 (58.5%) | 0 | 0 | 0 |

#### 4.4 `v2` Corpus Scaling (`cafe_01_x4` + `cafe_01_x16`, same 21 conversations / 28 turns; baseline: `orig`)

| Config | Original `v2` (`x4` + `x16`) | `scorer_v3` | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| `C0` | 43/56 (76.8%) | 43/56 (76.8%) | 0 | 0 | 0 |
| `C1` | 20/56 (35.7%) | 20/56 (35.7%) | 0 | 0 | 0 |
| `C2` | 13/56 (23.2%) | 13/56 (23.2%) | 0 | 0 | 0 |
| `C3` | 45/56 (80.4%) | 45/56 (80.4%) | 0 | 0 | 0 |
| `C4` | 43/56 (76.8%) | 43/56 (76.8%) | 0 | 0 | 0 |

#### 4.5 `v2` Frozen Held-Out Test Set (`data/test/landscaping_01`, run `20261119-010517`; baseline: `orig`)

| Config | Original `v2` | `scorer_v3` | Delta | Pass→Fail | Fail→Pass |
| --- | --- | --- | --- | --- | --- |
| `C0` | 25/40 (62.5%) | 25/40 (62.5%) | 0 | 0 | 0 |
| `C1` | 16/40 (40.0%) | 16/40 (40.0%) | 0 | 0 | 0 |
| `C2` | 20/40 (50.0%) | 20/40 (50.0%) | 0 | 0 | 0 |
| `C3` | 29/40 (72.5%) | 29/40 (72.5%) | 0 | 0 | 0 |
| `C4` | 27/40 (67.5%) | 27/40 (67.5%) | 0 | 0 | 0 |

**Key takeaway:** Zero held-out (`0/200`) and zero scaling (`0/280`) turn verdicts changed under `scorer_v3`. All `v2` `C0`, `C2`, `C3`, and `C4` totals across every standard stratum are invariant. The only 3 standard `v2` turns that flipped were `C1` turns (`cafe_01 Q17 t2`, `clinic_01 D214 t0`, `clinic_01 D214 t1`) where the model wrote a negative bank debit (`-300.00 USD` or `-550.00 USD`) and gold specified a positive amount (`300.00` or `550.00 USD`). Full row-level details are in `evaluation/results/scorer_v3/per_turn_changes.csv` and `per_turn_changes.md`.

---

## 5. Challenge Rescoring Reconciliation (`12/17` vs. `14/17`)

Inspecting `evaluation/results/challenge/20261119-110444-cafe_01` (and earlier `20261119-103951-cafe_01`) shows that the jump from **12/17** (`log.jsonl`) to **14/17** (`rescored/log.jsonl`) on `20261119-110444-cafe_01` arose entirely from **gold-file updates**, not changed model outputs:

1. **`CH5 t1` (`FAIL → PASS`):** Original gold required `['1462.85', '847.45']` (assuming a duplicate-payment credit would reduce the remaining open balance from `1462.85` to `847.45`). The model correctly noted that `NS-1031` already had `$0.00` remaining, so open bills remained `1462.85 USD`. Updating `cafe_challenge_gold.yaml` to require only `['1462.85 USD']` flipped `CH5 t1` to `PASS` (remains `PASS` under `scorer_v3`).
2. **`CH6 t0` (`FAIL → PASS`):** Original gold used bare `'1750.00'`, which failed against comma-formatted `'$1,750.00 USD'` under the old bare-number regex. Updating `cafe_challenge_gold.yaml` to `'1750.00 USD'` flipped `CH6 t0` to `PASS` (remains `PASS` under `scorer_v3` because the saved reply explicitly states `"$1,750.00 USD"` in addition to `"-1,750.00 USD"`).

On the earlier run `20261119-103951-cafe_01` (`8/17` orig → `14/17` prior rescored → `14/17` `scorer_v3`), two turns offset under `scorer_v3`:
- `CH1 t0` flipped `PASS → FAIL` because the reply declared `"(all USD)"` in a header and wrote bare per-bill numbers (`268.90`, `1073.25`, `389.60`, `512.30`, `212.30`) without `$` or `USD` attached to each amount.
- `CH6 t0` flipped `FAIL → PASS` due to the updated `'1750.00 USD'` gold entry.

Full per-turn challenge tables are in `evaluation/results/scorer_v3/challenge_analysis.md` and `challenge_analysis.json`.

---

## 6. Blinded Human-Review Packet

Generated under `evaluation/results/scorer_v3/human_review/` (seed `259`, all human columns left blank):
- `blind_verdict_changes.csv` (**10** turns — every verdict-changing turn across all strata) + separate `key_verdict_changes.csv`.
- `blind_unchanged_sample.csv` (**48** stratified unchanged turns, up to 4 per `(stratum, pass/fail)` bucket) + separate `key_unchanged_sample.csv`.
- Configuration (`C0`–`C4`), run ID, and automated verdicts are excluded from the blind CSVs and stored only in the separate key files.

---

## 7. Proposed Out-of-Ownership Follow-Up Patches (Documented, Not Edited)

Running `tests/test_challenge.py` against `scorer_v3` surfaced two legacy assertions in `code/tests/test_challenge.py` (outside this assignment's file ownership) that relied on the prior buggy scorer:
1. `code/tests/test_challenge.py:67` (`test_section_exclude_recipient_email_and_or_values`): `good_raw` writes `"GP-228 (212.30 or 512.30)"` without `$` or `USD` while `cafe_challenge_gold.yaml` expects `["212.30 USD", "512.30 USD"]`. Proposed patch: write `"GP-228 ($212.30 USD or $512.30 USD)"` in the test fixture.
2. `code/tests/test_challenge.py:554–559` (`test_money_values_have_currency_and_cafe_ch5_accepts_open_total`): tests that negative `"-1,750.00 USD"` matches positive `"1750.00 USD"` on `CH6 t0`. Proposed patch: either accept `["1750.00 USD", "-1750.00 USD"]` explicitly in `cafe_challenge_gold.yaml` for bank-debit queries (if signed negative debits are intended to pass), or update the test fixture to test `"-1750.00 USD"` against negative expected gold.
