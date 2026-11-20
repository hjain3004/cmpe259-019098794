# Scaling Preflight Report (Approximate Local Estimates)

- **Model target:** `claude-haiku-5-5`
- **Context limit used:** `1,000,000` tokens (documented `1M` capacity from Anthropic model overview; configurable via `--context-limit`); output reserve: `4,096` tokens
- **Long-context pricing threshold:** `100,000` total input tokens/request (cache reads + writes + uncached input count toward tier)
- **Published pricing cited (retrieved `2026-11-19`):** `<=100k`: `$0.10/M` in, `$0.50/M` out, `$0.125/M` 5m cache write, `$0.01/M` cache read; `>100k`: `$0.50/M` in, `$2.50/M` out, `$0.625/M` 5m cache write, `$0.05/M` cache read
- **Tokenizer check:** `approximate (character/table heuristic; no local Anthropic tokenizer installed)` — **all feasibility statuses are estimates, not guarantees**
- **Sources:** `https://platform.claude.com/docs/en/models/haiku-5-5/overview`, `https://platform.claude.com/docs/en/about-claude/pricing`

> **Tool-payload disclaimer:** `C3` is **not** constant-size when `list_open_bills(include_settled=True)` returns every bill in the corpus, nor on `seed=259` `x32`/`x64` where matching collisions inflate `include_settled=False` (`11` and `32` open bills). Shown `C3` single-request and multi-call numbers are sample estimates for a single call / 2-round loop, **not** verified upper bounds.

## 1. Actual On-Disk Bundles

| Bundle | Invoices / Bank | Open Bills (Gold Matcher) | C0 Req In (Approx / `chars/4`) | C0 >100k Tier? | C0 Est. Feasibility | C3 Open Req In | C3 Sample `include_settled` Req In | C3 `include_settled` >100k? | C3 Est. Feasibility |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- | --- |
| `cafe_01` | 8 / 15 | 5 | ~6,348 (~3,790) | no | **ESTIMATED_FEASIBLE** | ~5,927 | ~8,081 | no | **ESTIMATED_FEASIBLE** |
| `cafe_01_x4` | 32 / 69 | 5 | ~17,279 (~8,900) | no | **ESTIMATED_FEASIBLE** | ~5,927 | ~16,089 | no | **ESTIMATED_FEASIBLE** |
| `cafe_01_x16` | 128 / 285 | 5 | ~60,959 (~29,320) | no | **ESTIMATED_FEASIBLE** | ~5,927 | ~48,123 | no | **ESTIMATED_FEASIBLE** |
| `cafe_01_x32` | 256 / 573 | 11 | ~119,270 (~56,581) | YES (5x) | **ESTIMATED_FEASIBLE** | ~10,765 | ~93,570 | no | **ESTIMATED_FEASIBLE** |
| `cafe_01_x64` | 512 / 1149 | 32 | ~235,868 (~111,090) | YES (5x) | **ESTIMATED_FEASIBLE** | ~26,874 | ~187,883 | YES (5x) | **ESTIMATED_FEASIBLE** |

### Estimated Multi-Call Totals & USD Ranges (Approximate Only)

| Bundle | Extract Calls | Est. Extract USD Range | C0 Answering USD Range | C3 Summed Multi-Call In (Open / Settled Sample) | C3 Answering USD Range |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cafe_01` | 21 | $0.008–$0.011 | $0.040–$0.052 | ~14,818 / ~17,778 | $0.039–$0.066 |
| `cafe_01_x4` | 81 | $0.029–$0.042 | $0.070–$0.090 | ~14,818 / ~35,396 | $0.047–$0.076 |
| `cafe_01_x16` | 321 | $0.116–$0.166 | $0.192–$0.243 | ~14,818 / ~105,871 | $0.079–$0.116 |
| `cafe_01_x32` | 641 | $0.232–$0.332 | $1.778–$2.236 | ~26,912 / ~205,854 | $0.155–$0.687 |
| `cafe_01_x64` | 1281 | $0.464–$0.662 | $3.411–$4.277 | ~67,185 / ~413,343 | $1.101–$1.401 |
