# Scaling Preflight Report (Approximate Local Estimates)

- **Profile selection:** `controlled` (bundle profiles present: `baseline_x1`, `controlled`)
- **Configurations modeled:** `C0`, `C3`
- **Model target:** `claude-haiku-5-5`
- **Context limit used:** `1,000,000` tokens (documented `1M` capacity from Anthropic model overview; configurable via `--context-limit`); output reserve: `4,096` tokens
- **Long-context pricing threshold:** `100,000` total input tokens/request (cache reads + writes + uncached input count toward tier)
- **Published pricing cited (retrieved `2026-11-19`):** `<=100k`: `$0.10/M` in, `$0.50/M` out, `$0.125/M` 5m cache write, `$0.01/M` cache read; `>100k`: `$0.50/M` in, `$2.50/M` out, `$0.625/M` 5m cache write, `$0.05/M` cache read
- **Low/High range assumptions:** Low = warm 5m cache read after call 1, `1.0x` tokens, `0%` retries; High = `50%` cache writes / `50%` cache reads, `1.25x` token estimation margin, `1.15x` calls/output for retries & multi-round variance.
- **Tokenizer check:** `approximate (character/table heuristic; no local Anthropic tokenizer installed)` — **all feasibility statuses and dollar ranges are heuristic estimates, NOT enforced spending caps or guarantees.**
- **Sources:** `https://platform.claude.com/docs/en/models/haiku-5-5/overview`, `https://platform.claude.com/docs/en/about-claude/pricing`

- **Query slice structure:** `28` scored turns total (`27` predeclared invariant-task turns + `1` corpus-sensitive `Q13` turn across `21` conversations); all `28` turns are executed.
> **Tool-payload disclaimer:** On the `controlled` profile, `gold_open_bills` stays constant at `5` across scales, keeping `list_open_bills(include_settled=False)` bounded (`~5.9k` req in). However, `list_open_bills(include_settled=True)` returns all bills (`O(N_invoices)`) and crosses `100k` (5x tier) at `x64`. Shown `C3` numbers are sample estimates, **not** verified upper bounds.

## 1. Actual On-Disk Bundles

| Bundle (`Profile`) | Invoices / Bank | Open Bills (Gold Matcher) | `extracted.sqlite` On Disk | C0 Req In (Approx / `chars/4`) | C0 >100k Tier? | C0 Est. Feasibility | C3 Open Req In | C3 Sample `include_settled` Req In | C3 `include_settled` >100k? | C3 Est. Feasibility |
| --- | --- | ---: | --- | ---: | --- | --- | ---: | ---: | --- | --- |
| `cafe_01` (`baseline_x1`) | 8 / 15 | 5 | present | ~6,348 (~3,790) | no | **ESTIMATED_FEASIBLE** | ~5,927 | ~8,081 | no | **ESTIMATED_FEASIBLE** |
| `cafe_01_ctrl_x16` (`controlled`) | 128 / 285 | 5 | missing | ~61,409 (~29,530) | no | **ESTIMATED_FEASIBLE** | ~5,927 | ~48,123 | no | **ESTIMATED_FEASIBLE** |
| `cafe_01_ctrl_x64` (`controlled`) | 512 / 1149 | 5 | missing | ~237,755 (~111,972) | YES (5x) | **ESTIMATED_FEASIBLE** | ~5,927 | ~176,258 | YES (5x) | **ESTIMATED_FEASIBLE** |

### Estimated Workload, Retries & USD Ranges (Estimates Only, Not Enforced Caps)

| Bundle | Extract Calls (Fresh / Reuse-x1) | Est. Extract USD Range (Fresh / Reuse-x1) | C0 Calls (Nominal / +15% Retry) | C0 Answering USD Range | C3 Summed Multi-Call In (Open / Settled Sample) | C3 Calls (Nominal / +15% Retry) | C3 Answering USD Range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cafe_01` | 21 / 0 | $0.008–$0.013 / $0.000–$0.000 | 28 / 32 | $0.040–$0.060 | ~14,818 / ~17,778 | 72 / 83 | $0.039–$0.076 |
| `cafe_01_ctrl_x16` | 321 / 321 | $0.116–$0.191 / $0.116–$0.191 | 28 / 32 | $0.194–$0.280 | ~14,818 / ~105,871 | 72 / 83 | $0.079–$0.137 |
| `cafe_01_ctrl_x64` | 1281 / 1281 | $0.464–$0.762 / $0.464–$0.762 | 28 / 32 | $3.437–$4.927 | ~14,818 / ~387,768 | 72 / 83 | $0.913–$1.396 |

## 3. Aggregate Estimated Cost Ranges (Not Enforced Caps)

- **Extraction (`ctrl_x16` + `ctrl_x64`, reusing compatible `cafe_01` `x1` SQLite):** `$0.580–$0.953` (`$0.588–$0.965` if re-extracting `x1` fresh too)
- **Answering (C0, C3 across listed bundles):** `$4.702–$6.875` (`C0` `$3.670–$5.266`, `C3` `$1.032–$1.609`)
- **Combined Estimated Total (reuse `x1` SQLite / all fresh):** `$5.282–$7.828` / `$5.290–$7.841`
