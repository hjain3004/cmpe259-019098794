# Controlled Corpus-Volume Scaling Experiment Plan (`v3_1`)

This document specifies the reproducible **`v3_1` controlled-volume corpus-scaling evaluation** of CashBooks Assist (**`C0`** vs. **`C3`**) across the three verified on-disk controlled bundles up to `x64` (`512` invoices, `256` messages, `1,149` bank rows). **No paid extraction or answering API calls are executed by this plan.**

---

## 1. Bundle Paths & Experimental Profile Separation

### Controlled-Volume Curve (Primary Experiment — This Plan)

All three bundles are present on disk, share identical `gold.yaml` (`SHA-256: 76c7c12f...`) across `21` conversations (`28` scored turns), and pass offline `check_gold.py` and `validate_scaled_bundle.py`:

| Scale | Bundle Path | Profile | Corpus Counts | `open_bills` (Gold Matcher) | `extracted.sqlite` On Disk | Offline Validation Status |
| --- | --- | --- | --- | ---: | --- | --- |
| `x1` | `data/dev/cafe_01` | `baseline_x1` | `8` inv, `1` cred, `4` msg, `15` bank (`31` chunks) | `5` | **Present** (`c445dc0c...`, provenance-verified) | `check_gold.py`: OK |
| `x16` | `data/dev/cafe_01_ctrl_x16` | `controlled` | `128` inv, `1` cred, `64` msg, `285` bank (`481` chunks) | `5` | **Missing** (must build/extract) | Cat A: `PASS`; Cat B: `CLEAN (0 diffs)` |
| `x64` | `data/dev/cafe_01_ctrl_x64` | `controlled` | `512` inv, `1` cred, `256` msg, `1,149` bank (`1,921` chunks) | `5` | **Missing** (must build/extract) | Cat A: `PASS`; Cat B: `CLEAN (0 diffs)` |

- **Primary Research Question:** With active open bills (`5`) and gold truth (`gold.yaml`) held invariant while distractor history grows `1x -> 16x -> 64x`, does **`C3`** preserve task accuracy relative to **`C0`** while curbing input-token, long-context tier, and dollar growth?
- **Configurations under test:** **`C0`** (whole raw corpus in context) vs. **`C3`** (seven read-only SQLite/evidence tools over extracted records), both sharing `PROMPT_VERSION = "answer_system_v2"`, `MAX_TOKENS = 4096`, `MAX_TOOL_CALLS = 6`, and model `claude-haiku-5-5`.

### Ambiguity-Profile Stress Results (Strictly Separate)

The earlier `seed=259` `ambiguity`-profile bundles (`data/dev/cafe_01_x4`, `cafe_01_x16`, `cafe_01_x32`, `cafe_01_x64`) append background historical bills whose descriptors omit invoice numbers. Because `cafe_01_x32` and `cafe_01_x64` create amount collisions inside 45-day matching windows (`6` false-open bills at `x32`, `27` at `x64`, `docs/scaling_generator_validation.md`), they test **matching ambiguity under scale** rather than pure corpus volume:

- **Strict separation rules:**
  1. `data/dev/cafe_01_x16`, `cafe_01_x32`, and `cafe_01_x64` MUST NOT enter the controlled-volume curve.
  2. The legacy ambiguity preflight report at `evaluation/results/scaling_preflight/preflight_report.{json,md}` is preserved unchanged; controlled-volume preflight outputs live separately at `evaluation/results/scaling_preflight_ctrl_v3_1/preflight_report.{json,md}`.
  3. Never splice historical `v2` ambiguity runs onto new controlled `v3_1` runs.

---

## 2. Measured Historical Reference (`v2` / `v2_scaling`) vs. Preflight Estimates

### Measured Historical Runs (Reported Strictly as Historical Reference)

Historical runs executed before `scorer_v3_1` / `specs_v3_1` on `data/dev/cafe_01`, `cafe_01_x4`, and `cafe_01_x16` (`ambiguity` profile) are **measured**, not heuristic projections:

| Historical Run | Bundle | Extraction Run (Measured) | `C0` Answering (Measured) | `C3` Answering (Measured) |
| --- | --- | --- | --- | --- |
| `20261118-223250-cafe_01-claude-haiku-5-5` | `cafe_01` (`x1`) | `20261117-233405`: `86/87` (`98.9%`), `21` calls, `42,510` in / `10,516` out, `0` failed, `0` ungrounded | `20/28` (`71.4%`), `14/21` conv, `27/28` parsed, `28` calls, `178,006` in / `42,421` out (`max_in=6,890`, `max_out=3,453`), med `6.85s` | `22/28` (`78.6%`), `17/21` conv, `27/28` parsed, `70` calls, `280,487` in / `28,055` out (`max_in=20,602`, `max_out=1,658`), med `4.78s` |
| `20261119-001330-cafe_01_x4-claude-haiku-5-5` | `cafe_01_x4` (`x4`, ambiguity) | `20261119-000312`: `324/327` (`99.1%`), `81` calls, `164,402` in / `39,191` out, `0` failed, `0` ungrounded | `22/28` (`78.6%`), `17/21` conv, `28/28` parsed, `28` calls, `485,176` in / `48,520` out (`max_in=17,917`, `max_out=4,003`), med `7.31s` | `24/28` (`85.7%`), `18/21` conv, `28/28` parsed, `78` calls, `356,331` in / `28,463` out (`max_in=34,232`, `max_out=1,916`), med `5.11s` |
| `20261119-002636-cafe_01_x16-claude-haiku-5-5` | `cafe_01_x16` (`x16`, ambiguity) | `20261119-001329`: `1,284/1,287` (`99.8%`), `321` calls, `651,844` in / `153,732` out, `0` failed, `0` ungrounded | `21/28` (`75.0%`), `16/21` conv, `27/28` parsed, `28` calls, `1,710,422` in / `52,818` out (`max_in=61,922`, `max_out=4,096` cap hit), med `8.91s` | `21/28` (`75.0%`), `16/21` conv, `28/28` parsed, `71` calls, `446,479` in / `31,002` out (`max_in=91,011`, `max_out=2,794`), med `5.02s` |

*Why retrospective dollar totals cannot be computed from historical logs:* `ClaudeLLM._usage()` (`code/src/cashbooks/llm/claude.py:70-75`) sums `input_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens` into a single turn-level `LogRow.input_tokens`, discarding per-call `>100k` tier boundaries and cache-write vs. cache-read breakdowns.

---

## 3. Documented Model Specs, Context Feasibility & Controlled Preflight (Heuristic Estimates Only)

### Model & Tiered Pricing Parameters (Verified `2026-11-19`)

- **Model (`claude-haiku-5-5`):** Documented context window **`1,000,000` tokens** (`--context-limit 1000000` default; configurable via `--context-limit` if deployment limits differ). Output cap in `ClaudeLLM` is `MAX_TOKENS = 4096` (vs. `128K` model max).
- **5× Long-Context Pricing Cliff (`>100,000` total input tokens per API request):** Uncached input + cache write + cache read all count toward the `100,000`-token per-request threshold:
  - **`<=100k` tier:** `$0.10/M` input, `$0.50/M` output, `$0.125/M` 5-min cache write (`1.25x`), `$0.01/M` cache read (`0.1x`).
  - **`>100k` tier (5×):** `$0.50/M` input, `$2.50/M` output, `$0.625/M` 5-min cache write, `$0.05/M` cache read.
- **Tokenizer caveat:** No offline Anthropic tokenizer (`tiktoken`/`transformers` or SDK token count) is used locally; preflight estimates apply `3.6` chars/token prose + `1.87` chars/token CSV/JSON/tables. **All token and dollar numbers below are approximate local estimates, NOT guarantees or enforced spending caps.**

### Offline Preflight Results (`evaluation/results/scaling_preflight_ctrl_v3_1/preflight_report.md`)

Run offline against the three controlled bundles (`--profile controlled --configs C0 C3`):

| Bundle (`Profile`) | Invoices / Bank | Open Bills (Gold) | `extracted.sqlite` | `C0` Req In (Approx / `chars/4`) | `C0` `>100k` (5×)? | `C0` Est. Feasibility (`1M`) | `C3` Open Req In | `C3` Sample `include_settled=True` Req In | `C3` Settled `>100k` (5×)? | `C3` Est. Feasibility (`1M`) |
| --- | --- | ---: | --- | ---: | --- | --- | ---: | ---: | --- | --- |
| `cafe_01` (`baseline_x1`) | `8` / `15` | `5` | `present` | `~6,348` (`~3,790`) | `no` | **`ESTIMATED_FEASIBLE`** | `~5,927` | `~8,081` | `no` | **`ESTIMATED_FEASIBLE`** |
| `cafe_01_ctrl_x16` (`controlled`) | `128` / `285` | `5` | `missing` | `~61,409` (`~29,530`) | `no` | **`ESTIMATED_FEASIBLE`** | `~5,927` | `~48,123` | `no` | **`ESTIMATED_FEASIBLE`** |
| `cafe_01_ctrl_x64` (`controlled`) | `512` / `1149` | `5` | `missing` | `~237,755` (`~111,972`) | **YES (5×)** | **`ESTIMATED_FEASIBLE`** | `~5,927` | `~176,258` | **YES (5×)** | **`ESTIMATED_FEASIBLE`** |

**Tool-payload behavior under `controlled` scaling:**
- Because `gold_open_bills` remains `5` across `x1 -> x16 -> x64` (`Category B = CLEAN`), `list_open_bills(include_settled=False)` stays bounded at `~5,927` single-request input tokens (`~14,818` summed over a sample 2.5× multi-call turn), well below `100k`.
- Conversely, `list_open_bills(include_settled=True)` dumps all invoices (`320,659` JSON chars on `ctrl_x64`) and scales `O(N_invoices)`, reaching **`~176,258` tokens in one call (`~387,768` summed across multi-call re-sends)** and crossing the `100,000`-token 5× pricing tier at `x64`. Shown `C3` counts are sample estimates (`24` standard open turns + `4` settled-history turns at `2.6` avg calls/turn), not hard upper bounds.
- Overflow rule: if any request `input + 4096` exceeds an active `--context-limit` deployment cap, record it as `INFEASIBLE_FULL_CONTEXT` rather than truncating evidence or misscoring API errors as task failures.

---

## 4. Controlled Extraction Provenance & SQLite Reuse Rules

### Provenance Audit of On-Disk `extracted.sqlite` Files

1. **`data/dev/cafe_01/extracted.sqlite` (`SHA-256: c445dc0c535ff51ed8850f64c378f92368c61ead94e2faf92e673984dd1564b3`) — PROVENANCE-COMPATIBLE:**
   - Written at `2026-11-17 23:34:05` by extraction run `20261117-233405-extract-cafe_01-claude-haiku-5-5` (`86/87 = 98.9%`, `21` calls, `42,510` in / `10,516` out, `0` failed, `0` ungrounded).
   - `code/src/cashbooks/extract/`, `prompts/extract_*.md`, and `code/src/cashbooks/tools/matching.py` have zero commits or uncommitted edits after `081b05c` (`2026-11-17 17:40:35`), and re-running `link_payments(Store(conn, "cafe_01"))` against `cafe_01/extracted.sqlite` matches all `5` stored `payment_links` rows cleanly.
   - **Decision:** `data/dev/cafe_01/extracted.sqlite` may be reused cleanly for `x1` (`$0.00` marginal extraction cost), or re-extracted fresh (`21` calls, `~$0.008–$0.013`) if an all-fresh build is preferred.

2. **`data/dev/cafe_01_x16/extracted.sqlite` — FORBIDDEN TO SILENTLY REUSE:**
   - Although `cafe_01_x16` and `cafe_01_ctrl_x16` share identical invoice PDF text (`128/128` pages) and `messages.jsonl`, their `bank.csv` files differ (`controlled` appends paid invoice references to bank descriptors). Silently copying `cafe_01_x16/extracted.sqlite` would inject `ambiguity`-profile `bank_txns` and `payment_links` into the `controlled` experiment.

3. **`data/dev/cafe_01_ctrl_x16` and `data/dev/cafe_01_ctrl_x64` — MISSING ON DISK:**
   - **Standard reproducible option (recommended):** Run `evaluation/extract_bundle.py --llm claude` fresh on both `data/dev/cafe_01_ctrl_x16` (`321` LLM calls) and `data/dev/cafe_01_ctrl_x64` (`1,281` LLM calls) = **`1,602` calls** total (`1,623` if `cafe_01` is also re-extracted fresh).
   - **Deterministic cache-rebuild option for `cafe_01_ctrl_x16` only (saves `321` calls if desired):**
     Only if reusing verified non-bank extraction rows (`bills`, `bill_lines`, `credits`, `message_claims`, `documents`, `evidence_spans`, `vendors`, `vendor_aliases`, `vendor_fingerprints`) from `cafe_01_x16/extracted.sqlite`:
     1. Assert offline that PDF `page_texts` (`128/128`) and `messages.jsonl` match byte-for-byte between `cafe_01_x16` and `cafe_01_ctrl_x16`.
     2. Copy to `data/dev/cafe_01_ctrl_x16/extracted.sqlite` and purge `bank_txns` + `payment_links` (`DELETE FROM payment_links; DELETE FROM bank_txns;`).
     3. Ingest fresh `BankTxn` rows from `data/dev/cafe_01_ctrl_x16/bank.csv` via `cashbooks.ingest.bank_csv.read_bank_csv` and insert into SQLite.
     4. Recompute `payment_links` via `cashbooks.tools.matching.link_payments(Store(conn, "cafe_01"))` and insert them.
     5. Validate offline against `data/dev/cafe_01_ctrl_x16/gold.yaml` that `Store.open_bills` has `5` open bills (`0` false-open historical bills).
     *(Note: `cafe_01_ctrl_x64` has no prior `x64` extraction on disk, so its `1,281` extraction calls must always run fresh.)*

---

## 5. Recalculated Workload & Cost Ranges (Estimates Only, Not Enforced Caps)

Assumptions baked into `evaluation/scaling_preflight.py` (modeled at `--long-context-threshold 100000`):
- **Low bound:** 5-min ephemeral cache hit (`0.1x`) on shared prefix after call 1; `1.0x` heuristic tokens; `1.0x` calls (`0%` retries); output assumptions: extraction `480`/call, `C0` `1,800`/turn, `C3` `1,100` on `24` open turns + `1,450` on `4` settled turns.
- **High bound (uncertainty + retry sensitivity):** `50%` cache write / `50%` cache read mix + **`1.25x` token estimation margin** + **`1.15x` call/output retry multiplier** (modelling transient 429/5xx SDK retries up to `max_retries=6` or extra `C3` tool rounds).
- **Disclaimer:** All dollar ranges below are **heuristic preflight estimates for budget planning, NOT enforced API spending caps**.

| Stage / Item | Est. Calls (Nominal / +15% Retry) | Approx Heuristic Input Tokens | Approx Heuristic Output Tokens | Pricing Tier(s) | Est. USD Range (Not a Cap) |
| --- | ---: | ---: | ---: | --- | ---: |
| **Extraction — `x1` (`cafe_01` reused vs. fresh)** | `0` (`21` / `24` if fresh) | `0` (`~42.6k` fresh) | `0` (`~10.1k` fresh) | `<=100k` | **`$0.000`** (`$0.008–$0.013` fresh) |
| **Extraction — `x16` (`cafe_01_ctrl_x16`)** | `321` / `369` | `~651.6k` | `~154.1k` | `<=100k` | **`$0.116 – $0.191`** |
| **Extraction — `x64` (`cafe_01_ctrl_x64`)** | `1,281` / `1,473` | `~2.600M` | `~614.9k` | `<=100k` | **`$0.464 – $0.762`** |
| **Extraction Subtotal (reuse `x1` / all fresh)** | `1,602` / `1,842` (`1,623` / `1,866`) | `~3.252M` (`~3.295M`) | `~769.0k` (`~779.0k`) | `100% <=100k` | **`$0.580 – $0.953`** (`$0.588–$0.965`) |
| **Answering `C0` (`x1`)** | `28` / `32` | `~177.7k` | `~50.4k` | `<=100k` | **`$0.040 – $0.060`** |
| **Answering `C0` (`cafe_01_ctrl_x16`)** | `28` / `32` | `~1.719M` | `~50.4k` | `<=100k` | **`$0.194 – $0.280`** |
| **Answering `C0` (`cafe_01_ctrl_x64`)** | `28` / `32` | `~6.657M` | `~50.4k` | **`100% >100k` (5×)** | **`$3.437 – $4.927`** |
| **Answering `C3` (`x1`)** | `72` / `83` | `~426.7k` | `~32.2k` | `<=100k` | **`$0.039 – $0.076`** |
| **Answering `C3` (`cafe_01_ctrl_x16`)** | `72` / `83` | `~779.1k` | `~32.2k` | `<=100k` | **`$0.079 – $0.137`** |
| **Answering `C3` (`cafe_01_ctrl_x64`)** | `72` / `83` | `~1.907M` | `~32.2k` | `24` open `<=100k`; **`4` settled `>100k` (5×)** | **`$0.913 – $1.396`** |
| **Answering Subtotal (`C0` + `C3`, `x1`/`x16`/`x64`)** | `300` / `345` | `~11.67M` | `~247.8k` | Mixed (`x64` triggers 5× tier) | **`$4.702 – $6.875`** (`C0`: `$3.670–$5.266`; `C3`: `$1.032–$1.609`) |
| **Combined Total (reuse `x1` SQLite / all fresh)** | `1,902` / `2,187` (`1,923` / `2,211`) | `~14.92M` (`~14.96M`) | `~1.017M` (`~1.027M`) | Mixed | **`$5.282 – $7.828`** (`$5.290 – $7.841`) |

*(Optional `C1`+`C2` additions stay in `<=100k` at `~$0.024–$0.039` per bundle per config; optional `R=3` repeats scale answering costs roughly linearly and do not increase independent `N=21` conversations.)*

---

## 6. Scorer Selection, Policy Interface & `Q13` Sensitivity Reporting

### Scorer & Spec Interface (`scorer_v3_1` + `specs_v3_1`)

- **Active Scorer:** `SCORER_VERSION = "scorer_v3_1"` (`code/src/cashbooks/scoring.py`).
- **Explicit Policy Selection:** Pass `--eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml` to `evaluation/run_eval.py` (`code/src/cashbooks/eval_specs.py`):
  - Resolves `cafe_01`, `cafe_01_ctrl_x16`, and `cafe_01_ctrl_x64` explicitly to scenario `cafe_01` via `bundle_to_scenario` (no suffix stripping).
  - Applies `overrides.cafe_01.Q17[2].payment` (`kind: txn_magnitude`, `value: "300.00"`) identically across `x1`, `x16`, and `x64` without altering `gold.yaml`.
  - Records `scoring_policy: "with_specs_v3_1"`, `spec_sha256`, `scorer_version`, and hashes into `metadata.json` and `summary.md`.
- *(If `--eval-spec` were omitted, `run_eval.py` would fall back to `strict_historical` default.)*

### `Q13` Corpus-Sensitivity Reporting Protocol

All `28` scored turns (`21` conversations) are executed at every scale (`cafe_01`, `cafe_01_ctrl_x16`, `cafe_01_ctrl_x64`). Because `Q13` compares `BW-771` against historical BeanWorks invoices whose prior range expands under controlled scaling (`1` prior `486.00` invoice at `x1` -> `41` prior [`126.00..525.00`] at `ctrl_x16` -> `169` prior [`90.00..525.00`] at `ctrl_x64`), **`run_eval.py --eval-spec` automatically separates `Q13` in `metadata.json` and `summary.md`**:
1. **All 28 turns** (`Q01..Q20, Q29, Q30` — full benchmark total).
2. **Predeclared 27-turn invariant-task subset** (excluding `Q13` on scaled bundles `ctrl_x16` and `ctrl_x64`).
3. **`Q13` alone** (`1/1` turn, with historical-comparison context shift disclosed).

### Statistical & Operational Reporting Rules

- Keep controlled-volume results separate from `ambiguity`-profile stress results and historical `v2` logs.
- Use `evaluation/stats.py` per scale (`N=21` conversation clusters, exact McNemar + 10,000-resample cluster bootstrap) — never pool repeated scales as independent queries.
- Report parsed rates (`invalid_json`, `4096` output truncation), per-stage tokens (`extraction` separate from `answering`), `>100k` 5× tier triggers, and median/`p90`/max latency.

---

## 7. Unified Execution Manifest (`v3_1` Controlled-Volume Curve)

| Manifest Field | Exact Value / Specification |
| --- | --- |
| **Working Directory** | `/Users/himanshu_jain/NLP_Project_Himanshu_Jain/cmpe259-019098794/project` |
| **Python Environment** | `../.venv/bin/python` |
| **Target Bundles & Profiles** | `data/dev/cafe_01` (`baseline_x1`), `data/dev/cafe_01_ctrl_x16` (`controlled`), `data/dev/cafe_01_ctrl_x64` (`controlled`) |
| **Configurations** | `C0` (full raw context), `C3` (read-only tools over `extracted.sqlite`) |
| **Model & Limits** | `claude-haiku-5-5`, `MAX_TOKENS = 4096`, `MAX_TOOL_CALLS = 6`, `--context-limit 1000000`, `--long-context-threshold 100000` |
| **Queries & Counts** | `evaluation/queries.yaml` (`SHA-256: 854791fa81567b616de8396df1327ea6549f907851caa49990f994d5a4d30a8f`) — `21` conversations / `28` scored turns (`27` invariant + `1` `Q13`) |
| **Prompts & Versions** | `answer_system_v2` (`prompts/answer_system_v2.md`, `39163e9376cea013c088f5cfeaae80c1d24e89e8454bd1a12798dd4aeaeffb4c`); `extract_invoice_header_v1` (`10df470df437a76c81d9b8e6e0dfc19e757fb1731876e7f57fc530d1a52295ed`), `extract_line_items_v1` (`cf68a93c2cdeb7d683a96d66a33e4ba1afd966856d908c1880b5b3d358c289c4`), `extract_credit_note_v1` (`c425a509302127a26572b14b2bf34c715d6858a1d782c32f972f6968dc417f95`), `extract_message_claim_v1` (`f23f7317dccc33e91d3a623c5c452473e05fa8faab61ddb9aa76242a5e76c4c7`) |
| **Scorer & Spec Policy** | `scorer_v3_1` (`code/src/cashbooks/scoring.py`, `204198e75620e78f4408329a167f22a7131f0e1243f88ef91e7a1b17a081a646`) + `specs_v3_1` (`evaluation/specs_v3_1/amount_semantics_overrides.yaml`, `36a8f37c7f0e805a2bf4ff4a44415db167fc33ace9e6b92311ae16da9d25b05c`; `manifest.json`, `64971446e90f5c7903693f5937a5a94613db94588a9520541b8305cd60d4779b`) |
| **Key Code & Generator Hashes** | `data/generator/scale_bundle.py` (`59dd2b12dfb7dcf76b220ace5855757d12ff3fd3da3d4666051da7e8ec0ebe3e`), `evaluation/validate_scaled_bundle.py` (`f85fa372418524d6d6d23e41104f5d615d2725c7825cb184836e98dafe14daf`), `evaluation/run_eval.py` (`72fc136182c840723069f5cc13fd276300a24ef8a5929e00bb534a3cf4f23947`), `evaluation/scaling_preflight.py` (`1d57d21367f7b69e106854e6311ba5a4b0c51de4164f8589a8c901cf96cf6882`), `code/src/cashbooks/configs/answer.py` (`2e7da3a2b27014eb2adc25c4d4b3a9bef1d73fddebc024306125923ea001f743`), `code/src/cashbooks/configs/dialogue_state.py` (`c1a29e0e4d255bcc05451a794a3f222f2229c5148ef716abf5da1bd81c9a43a2`), `code/src/cashbooks/contracts/postprocess.py` (`3850a577c753d61c4a26718bf8647db304c3fa961fe315c88c0b19255eda691d`), `code/src/cashbooks/extract/pipeline.py` (`693df811b377c0609c85b019308b316d6be037714942cbf76548b98037e1b274`), `code/src/cashbooks/tools/matching.py` (`18332ae4812b2abce8433eb0870d13f72c46a3f32caf3f0165b4b7caf59ed32c`) |
| **Bundle Artifact Hashes** | `cafe_01/ledger.json` (`75a41f8d4e936f172176cabb675d1b77d36492754873be2c567e970bc40e3725`), `cafe_01/extracted.sqlite` (`c445dc0c535ff51ed8850f64c378f92368c61ead94e2faf92e673984dd1564b3`), `cafe_01_ctrl_x16/ledger.json` (`2cfecbd229df7653cc5cdce9e98baf9bde02bc33d60774372ea3fafff1ef4b73`), `cafe_01_ctrl_x64/ledger.json` (`4933f0fc0798433976aa264396aa66887194baf3b9cceab6f8df3ee3df46bd6b`), shared `gold.yaml` (`76c7c12f89b116254243c1497c651bdf24a9a1163317e2a93e12caa88e1f4858`) |
| **Extraction Requirements** | Reuse compatible `data/dev/cafe_01/extracted.sqlite` (`0` calls) OR run fresh (`21` calls); extract `cafe_01_ctrl_x16` (`321` calls) & `cafe_01_ctrl_x64` (`1,281` calls) -> `1,602` calls (`1,623` all fresh) |
| **Preflight Outputs** | `evaluation/results/scaling_preflight_ctrl_v3_1/preflight_report.json` (`5680a0953e38373dcd39d2e47a5f442e457d60b72585b25c095f2eead1f5ccb8`) & `preflight_report.md` (`70c0fc93d9e842a5c7a84c2907d512a46aeaa3c77685d93059d02af9a1130c2f`) |
| **Estimated Cost Range (Not a Cap)** | Reuse `x1` SQLite: **`$5.282 – $7.828`** (`$0.580–$0.953` extract + `$4.702–$6.875` answering); all fresh: **`$5.290 – $7.841`** |

### Exact Offline & Proposed Execution Commands (Paid Steps Not Executed)

```zsh
# [OFFLINE - ALREADY VERIFIED PASSING] Gold checks, controlled Cat A/Cat B validation, and preflight
../.venv/bin/python data/generator/check_gold.py data/dev/cafe_01 data/dev/cafe_01_ctrl_x16 data/dev/cafe_01_ctrl_x64
../.venv/bin/python evaluation/validate_scaled_bundle.py data/dev/cafe_01 data/dev/cafe_01_ctrl_x16
../.venv/bin/python evaluation/validate_scaled_bundle.py data/dev/cafe_01 data/dev/cafe_01_ctrl_x64
../.venv/bin/python evaluation/scaling_preflight.py \
    data/dev/cafe_01 data/dev/cafe_01_ctrl_x16 data/dev/cafe_01_ctrl_x64 \
    --profile controlled --configs C0 C3 \
    --out-dir evaluation/results/scaling_preflight_ctrl_v3_1

# [PAID EXTRACTION - PROPOSED, NOT EXECUTED] Extract controlled x16 and x64
# (Add cafe_01 only if an all-fresh x1 extraction is desired instead of reusing c445dc0c...)
../.venv/bin/python evaluation/extract_bundle.py data/dev/cafe_01_ctrl_x16 --llm claude
../.venv/bin/python evaluation/extract_bundle.py data/dev/cafe_01_ctrl_x64 --llm claude

# [PAID ANSWERING - PROPOSED, NOT EXECUTED] Controlled curve C0 vs C3 under scorer_v3_1 + specs_v3_1
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01 \
    --configs C0 C3 --llm claude \
    --eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01_ctrl_x16 \
    --configs C0 C3 --llm claude \
    --eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01_ctrl_x64 \
    --configs C0 C3 --llm claude \
    --eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml

# [OFFLINE POST-RUN ANALYSIS - PROPOSED] Cluster-paired stats per scale
../.venv/bin/python evaluation/stats.py evaluation/results/<v3_1_x1_run>
../.venv/bin/python evaluation/stats.py evaluation/results/<v3_1_ctrl_x16_run>
../.venv/bin/python evaluation/stats.py evaluation/results/<v3_1_ctrl_x64_run>
```
