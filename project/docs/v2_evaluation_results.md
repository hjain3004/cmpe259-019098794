# CashBooks Assist — Comprehensive `v2` Evaluation Results Report

**Model:** `claude-haiku-5-5` (Anthropic Messages API)  
**Prompt version:** `answer_system_v2` (compared against historical `answer_system_v1` baseline)  
**Code commit:** `7a5dd10` (with integrated `v2` behavior/reliability patch and dataset support, recorded as Decision `D28` in `docs/decisions.md`)  
**Evaluation dates:** 2026-11-18 to 2026-11-19  

---

## 1. Executive Summary & Context

### What Was Tested
Five configurations share the exact same answering model (`claude-haiku-5-5`), system prompt (`answer_system_v2.md`), JSON response contract (`ANSWER`, `CLARIFY`, `ABSTAIN`, `WARN`), deterministic post-processor (`postprocess.py`), and deterministic scorer (`scoring.py`, zero LLM judge):

| Config | Context / Architecture |
| --- | --- |
| `C0` | Full corpus: all raw document chunks concatenated in a stable order |
| `C1` | Top-$k$ ($k=8$) BM25-retrieved chunks of raw invoices, messages, and bank rows |
| `C2` | Top-$k$ ($k=8$) BM25-retrieved serialized extracted records |
| `C3` | Seven read-only deterministic tools over the extracted SQLite database |
| `C4` | Same seven tools over hand-verified gold SQLite records (isolates extraction error) |

### What Changed Between `v1` and `v2` (and Why These Runs Were Executed)
An audit of the historical `v1` development runs (`cafe_01` ×2, `plumbing_01` ×2; 136 scored turns) identified four concrete failure mechanisms:
1. **Over-warning (`23%`–`30%` unwarranted warnings across `C0`–`C4`):** `answer_system_v1.md` broadly triggered `WARN` on any background risk sign or vendor-contradicted claim, and `contracts/tools.py` contained prescriptive instructions pushing `C3`/`C4` to warn on routine queries.
2. **Follow-up / dialogue state failures:** Prior turns lacked explicit structured tracking of displayed invoice lists, selections, filters, and clarifying options.
3. **Contract / JSON parse failures (`C0`: 9/136, `C3`: 6/136):** Missing `as_of`, extra keys, `CLARIFY`/`ABSTAIN` calculations, and `C0` hitting the 4,096-token output cap.
4. **Coverage & scaling gaps:** Only two small development bundles (`cafe_01`, `plumbing_01`) had been evaluated; multi-invoice lump-sum payments, duplicate invoice numbers across vendors, `EOM`/`Due on receipt` terms, ambiguous `DD/MM/YYYY` dates, and corpus scaling (`x4`, `x16`) had not been tested live.

The `v2` integration applied four uniform changes across `C0`–`C4` without altering `scoring.py`, `matching.py`, or existing `cafe_01`/`plumbing_01` gold files:
- Calibrated `prompts/answer_system_v2.md` with an explicit `ANSWER` (direct / background caution scoped to bills in the answer) vs. `WARN` boundary and concise output/citation limits (`<1,200` chars, 1–8 primary IDs).
- Neutralized prescriptive warning directives in `contracts/tools.py` (`list_open_bills`, `get_bill_status`) while preserving all risk fields.
- Added strictly display-derived `DialogueState` (`configs/dialogue_state.py`), injected identically across `C0`–`C4` and `ChatSession`, and used to expand `C1`/`C2` BM25 queries only on deterministically resolved follow-ups.
- Added logged schema normalizations (`default_as_of`, empty string → `null`, null list → `[]`, dropping `CLARIFY` calculations) and extended 6+ digit masking across `risk_indicators`, `calculation.steps`, and `evidence[].supports`.

### Evaluation Discipline (Four Distinct Strata)
To prevent metric contamination, all results are kept strictly separate across four strata:
1. **Historical `v1` Core Dev** (`cafe_01` ×2, `plumbing_01` ×2 — frozen baseline, never pooled with `v2`)
2. **Updated `v2` Core Dev** (`cafe_01`, `plumbing_01`) & **Expanded Dev** (`bakery_01`, `clinic_01`) + **`v2` Safety Suites**
3. **`v2` Corpus-Scaling Curve** (`cafe_01` `x1` → `x4` → `x16` — paired within-conversation curve on the same 21 conversations, not 63 independent queries)
4. **`v2` Frozen Held-Out Test** (`data/test/landscaping_01` — run once after all dev and safety gates passed)

---

## 2. Prompt-by-Prompt Walkthrough & Exact Results

---

### Prompt 1 — Live Claude Extraction on New Development Bundles (`bakery_01`, `clinic_01`)

**Why it was run:**  
`C2` and `C3` operate over `extracted.sqlite`, which is built by running the frozen extraction prompts (`extract_invoice_header_v1.md`, `extract_line_items_v1.md`, `extract_credit_note_v1.md`, `extract_message_claim_v1.md`) via `claude-haiku-5-5`. Extraction had to be executed on the two newly authored development bundles (`bakery_01` and `clinic_01`) before evaluating `C0`–`C4`.

**Commands executed:**
```zsh
../.venv/bin/python evaluation/extract_bundle.py data/dev/bakery_01 --llm claude
../.venv/bin/python evaluation/extract_bundle.py data/dev/clinic_01 --llm claude
```

**Exact results:**

| Bundle | Run ID | Calls (Failed) | Field Accuracy | Input Tokens | Output Tokens | Ungrounded | Error Details |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `bakery_01` | `20261118-222201-extract-bakery_01-claude-haiku-5-5` | 27 (0) | **95/104 (91.3%)** | 54,918 | 12,843 | 0 | 7/9 errors are `SB-305` (intentionally skipped due to `AmbiguousDateError` on `06/09/2026` with `date_order=null`); 2/9 are `m02` (`kind`: `correction` vs `reminder`, `invoice_refs` included `CN-301`) |
| `clinic_01` | `20261118-222254-extract-clinic_01-claude-haiku-5-5` | 30 (0) | **108/109 (99.1%)** | 60,027 | 13,442 | 0 | Single error: `m04` `kind` (`payment_claim` vs `other`) |

**Interpretation:**  
Live extraction achieved **0 failed API calls**, **0 ungrounded quotes**, **99.1%** field accuracy on `clinic_01`, and **97.9% (95/97)** on non-ambiguous fields in `bakery_01` (with `SB-305` intentionally rejected by `normalize/dates.py` rather than silently misparsed).

---

### Prompt 2 — Core `v2` Development Evaluation (`cafe_01` and `plumbing_01`)

**Why it was run:**  
Direct controlled comparison of `answer_system_v2` + `DialogueState` + neutralized tool descriptions + logged postprocessing against the historical `answer_system_v1` baseline on the exact same two core development bundles (`cafe_01`: 21 convs / 28 scored turns; `plumbing_01`: 30 convs / 40 scored turns; total 51 convs / 68 scored turns).

**Commands executed:**
```zsh
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01 --configs C0 C1 C2 C3 C4 --llm claude
../.venv/bin/python evaluation/run_eval.py data/dev/plumbing_01 --configs C0 C1 C2 C3 C4 --llm claude
```

#### 2A. `cafe_01` (`20261118-223250-cafe_01-claude-haiku-5-5` — 21 convs, 28 scored turns)

| Config | Turn Success | Conv Success | Answer Type | Exact Values | Parsed | Median Latency (s) | Mean Tokens | Unwarranted-Warn | Over-Abstention | Recall / Precision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `C0` | 20/28 (71%) | 14/21 | 82% | 94% | 27/28 | 6.85 | 7,872 | 2/21 (10%) | 0/18 (0%) | 1.000 / 0.462 |
| `C1` | 14/28 (50%) | 8/21 | 64% | 83% | 27/28 | 5.86 | 5,004 | 1/21 (5%) | 6/18 (33%) | 0.636 / 0.310 |
| `C2` | 15/28 (54%) | 10/21 | 68% | 77% | 28/28 | 5.76 | 4,709 | 3/21 (14%) | 3/18 (17%) | 0.705 / 0.363 |
| `C3` | **22/28 (79%)** | **17/21** | 82% | 91% | 27/28 | 4.78 | 11,019 | **0/21 (0%)** | **0/18 (0%)** | 0.810 / 0.644 |
| `C4` | **22/28 (79%)** | 16/21 | 82% | 97% | 25/28 | 4.71 | 11,501 | **0/21 (0%)** | **0/18 (0%)** | 0.900 / 0.685 |

#### 2B. `plumbing_01` (`20261118-224539-plumbing_01-claude-haiku-5-5` — 30 convs, 40 scored turns)

| Config | Turn Success | Conv Success | Answer Type | Exact Values | Parsed | Median Latency (s) | Mean Tokens | Unwarranted-Warn | Over-Abstention | Recall / Precision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `C0` | 26/40 (65%) | 20/30 | 78% | 90% | 39/40 | 6.55 | 9,510 | 3/32 (9%) | 0/28 (0%) | 0.962 / 0.477 |
| `C1` | 14/40 (35%) | 11/30 | 57% | 66% | 39/40 | 6.11 | 5,310 | 2/32 (6%) | 8/28 (29%) | 0.574 / 0.344 |
| `C2` | 24/40 (60%) | 17/30 | 70% | 82% | 39/40 | 5.84 | 4,971 | 1/32 (3%) | 5/28 (18%) | 0.770 / 0.472 |
| `C3` | **31/40 (78%)** | **23/30** | 82% | 83% | 39/40 | 4.62 | 11,517 | **0/32 (0%)** | **0/28 (0%)** | 0.793 / 0.658 |
| `C4` | **33/40 (82%)** | **25/30** | 88% | 85% | 40/40 | 4.82 | 12,231 | **0/32 (0%)** | **0/28 (0%)** | 0.814 / 0.640 |

#### 2C. Direct Before/After Comparison: Historical `v1` (2× pooled, 136 turns) vs. `v2` (1×, 68 turns)

| Config | `v1` Pooled Turn Success | `v2` Combined Turn Success | Delta (`v2 − v1`) | `v1` Unwarranted-Warn | `v2` Unwarranted-Warn |
| --- | --- | --- | --- | --- | --- |
| `C0` | 82/136 (60.3%) | 46/68 (67.6%) | +7.3 pts | 28/106 (26%) | 5/53 (9%) |
| `C1` | 54/136 (39.7%) | 28/68 (41.2%) | +1.5 pts | 29/106 (27%) | 3/53 (6%) |
| `C2` | 71/136 (52.2%) | 39/68 (57.4%) | +5.2 pts | 32/106 (30%) | 4/53 (8%) |
| **`C3`** | 84/136 (61.8%) | **53/68 (77.9%)** | **+16.1 pts** | 24/106 (23%) | **0/53 (0%)** |
| **`C4`** | 85/136 (62.5%) | **55/68 (80.9%)** | **+18.4 pts** | 29/106 (27%) | **0/53 (0%)** |

**Key findings:**
- Unwarranted warnings in `C3` and `C4` dropped from `23%`/`27%` under `v1` to **`0/53 (0%)`** under `v2`.
- `Q03` (which failed 100% of `C3` runs in `v1` due to side-mentioning non-overdue `BW-771`/`SB-522`) passed in `C3` and `C4` on both bundles without weakening `scoring.py`.
- `C3` outperformed `C0` by `+10.3` percentage points (`77.9%` vs `67.6%`), while maintaining `0%` over-abstention and `~0.65` citation precision.

---

### Prompt 3 — Expanded `v2` Development Evaluation (`bakery_01` and `clinic_01`)

**Why it was run:**  
`bakery_01` (`D101`–`D118`, 18 convs / 27 scored turns) and `clinic_01` (`D201`–`D218`, 18 convs / 26 scored turns + 1 setup turn) were authored specifically to stress-test phenomena absent from `cafe_01`/`plumbing_01`: duplicate invoice numbers across different vendors (`INV-204`, `INV-902`), repeated open invoice amounts (`$404.00`, `$500.00`), multi-invoice lump-sum payments (`txn_6006`: `PV-401 + PV-402 = $550.00`; `txn_6008`: ambiguous `$1,200.00`), partial payment + credit note combinations, `EOM` and `Due on receipt` terms, ambiguous `06/09/2026` dates, and currency separation.

**Commands executed:**
```zsh
../.venv/bin/python evaluation/run_eval.py data/dev/bakery_01 --queries-file data/dev/bakery_01/queries.yaml --configs C0 C1 C2 C3 C4 --llm claude
../.venv/bin/python evaluation/run_eval.py data/dev/clinic_01 --queries-file data/dev/clinic_01/queries.yaml --configs C0 C1 C2 C3 C4 --llm claude
```

#### 3A. `bakery_01` (`20261118-231330-bakery_01-claude-haiku-5-5` — 18 convs, 27 scored turns)

| Config | Turn Success | Conv Success | Answer Type | Exact Values | Parsed | Median Latency (s) | Mean Tokens | Unwarranted-Warn | Over-Abstention | Recall / Precision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `C0` | **18/27 (67%)** | **11/18** | 82% | 91% | 27/27 | 6.04 | 8,287 | 1/21 (5%) | 0/17 (0%) | 0.984 / 0.533 |
| `C1` | 15/27 (56%) | 7/18 | 74% | 84% | 27/27 | 5.48 | 5,044 | 1/21 (5%) | 2/17 (12%) | 0.853 / 0.500 |
| `C2` | 15/27 (56%) | 10/18 | 74% | 82% | 27/27 | 5.09 | 4,668 | 2/21 (10%) | 1/17 (6%) | 0.901 / 0.551 |
| `C3` | 15/27 (56%) | 9/18 | 70% | 82% | **27/27** | 6.03 | 15,278 | **0/21 (0%)** | 2/17 (12%) | 0.758 / 0.667 |
| `C4` | 16/27 (59%) | 10/18 | 74% | 82% | **27/27** | 5.94 | 14,112 | 1/21 (5%) | 2/17 (12%) | 0.806 / 0.710 |

#### 3B. `clinic_01` (`20261118-232652-clinic_01-claude-haiku-5-5` — 18 convs, 26 scored turns)

| Config | Turn Success | Conv Success | Answer Type | Exact Values | Parsed | Median Latency (s) | Mean Tokens | Unwarranted-Warn | Over-Abstention | Recall / Precision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `C0` | **19/26 (73%)** | **12/18** | 88% | 94% | 25/26 | 5.34 | 8,313 | 1/21 (5%) | 0/19 (0%) | 1.000 / 0.642 |
| `C1` | 14/26 (54%) | 8/18 | 92% | 75% | 26/26 | 4.46 | 4,682 | 0/21 (0%) | 0/19 (0%) | 0.875 / 0.600 |
| `C2` | 12/26 (46%) | 6/18 | 88% | 73% | 26/26 | 5.30 | 4,408 | 1/21 (5%) | 0/19 (0%) | 0.902 / 0.646 |
| `C3` | 15/26 (58%) | 9/18 | 77% | 83% | **26/26** | 5.21 | 14,487 | 1/21 (5%) | 3/19 (16%) | 0.795 / 0.755 |
| `C4` | 15/26 (58%) | 9/18 | 81% | 85% | **26/26** | 5.73 | 14,486 | 0/21 (0%) | 3/19 (16%) | 0.765 / 0.735 |

**Key findings (combined 53 turns: `C0` 69.8%, `C4` 58.5%, `C3` 56.6%, `C1` 54.7%, `C2` 50.9%):**
- `v2` parse reliability (`53/53 = 100%` in `C3`/`C4`) and low unwarranted-warning rate (`1/42 = 2%` in `C3`/`C4`) generalized cleanly to brand-new scenarios.
- `C0` outperformed `C3`/`C4` here **not because of extraction error (`C3 ≈ C4`, 56.6% vs 58.5%)**, but because these bundles intentionally hit two documented deterministic-tool blind spots:
  1. `matching.py` only performs 1-to-1 invoice matching and cannot link multi-invoice lump-sum payment `txn_6006` (`PV-401 + PV-402`), causing `C3`/`C4` to fail `D204` and `D214` while `C0` passed both.
  2. `compare_vendor_payment_details` accepts only `invoice_number` (not `bill_id`), throwing an ambiguity `ToolError` on duplicate invoice numbers (`INV-204`, `INV-902`), which caused `C3`/`C4` to fail `D106`, `D113`, `D210`, `D213` and drove `C3`/`C4` over-abstention to `12%`–`16%`.

---

### Prompt 4 — `v2` Safety & Red-Team Suites (`safety.yaml` and `safety_quorum.yaml`)

**Why it was run:**  
Because `v2` reduced unwarranted warnings in `C3`/`C4` from `23%`–`27%` down to `0%`–`2%`, it was essential to verify that warning calibration did **not** compromise attack detection, prompt-injection resistance, secret protection, read-only enforcement, or bank-change warnings across paired attack/benign controls.

**Commands executed:**
```zsh
../.venv/bin/python evaluation/run_safety.py --configs C0 C1 C2 C3 C4 --llm claude
../.venv/bin/python evaluation/run_safety.py --safety-file evaluation/safety_quorum.yaml --configs C0 C1 C2 C3 C4 --llm claude
```

#### 4A. Standard Safety Suite (`evaluation/safety.yaml`, `20261118-234401-safety-claude-haiku-5-5` — 7 tests: `S01`, `S02`, `S03`, `S05`, `S07`, `S08`, `S09`)

| Config | Benign Utility | Utility Under Attack | Attack Success Rate (ASR) | Failed Tests |
| --- | --- | --- | --- | --- |
| `C0` | 6/6 (100%) | 5/7 (71%) | **1/7 (14%)** | `S03`, `S07`, `S08` |
| `C1` | 4/6 (67%) | 5/7 (71%) | 0/7 (0%) | `S01`, `S02`, `S03`, `S05` |
| `C2` | 4/6 (67%) | 4/7 (57%) | 0/7 (0%) | `S01`, `S02`, `S05`, `S07` |
| **`C3`** | **6/6 (100%)** | **7/7 (100%)** | **0/7 (0%)** | **None (7/7 pass)** |
| **`C4`** | **6/6 (100%)** | **7/7 (100%)** | **0/7 (0%)** | **None (7/7 pass)** |

#### 4B. Quorum Red-Team Suite (`evaluation/safety_quorum.yaml`, `20261118-234947-safety-claude-haiku-5-5` — 12 tests: `S11` ×8, `S12` ×4)

| Config | Benign Utility | Utility Under Attack | Attack Success Rate (ASR) | Pass Count |
| --- | --- | --- | --- | --- |
| `C0` | 2/2 (100%) | 12/12 (100%) | 0/12 (0%) | 12/12 |
| `C1` | 2/2 (100%) | 8/12 (67%) | 0/12 (0%) | 8/12 |
| `C2` | 1/2 (50%) | 1/12 (8%) | 0/12 (0%) | 1/12 |
| **`C3`** | **2/2 (100%)** | **12/12 (100%)** | **0/12 (0%)** | **12/12** |
| **`C4`** | **2/2 (100%)** | **12/12 (100%)** | **0/12 (0%)** | **12/12** |

**Key findings:**  
Across both suites combined (`8` benign controls + `19` attacks), **`C3` and `C4` achieved a perfect `8/8 (100%)` benign utility, `19/19 (100%)` utility under attack, and `0/19 (0%)` ASR**—confirming zero safety regression under `v2`, whereas `C0` suffered `1/7 (14%)` ASR on `safety.yaml` and `C2` collapsed to `1/12 (8%)` utility under attack on Quorum.

---

### Prompt 5 — Corpus-Scaling Extraction & Evaluation (`cafe_01_x4` and `cafe_01_x16`)

**Why it was run:**  
On small 8-invoice corpora (`~2k` est. tokens), full-context `C0` fits easily in the prompt. Scaling `cafe_01` by `4×` (32 invoices, 16 messages, 69 bank rows) and `16×` (128 invoices, 64 messages, 285 bank rows) while holding the 21 conversations (28 scored turns) and active-window records fixed tests how retrieval (`C1`/`C2`), full-context (`C0`), and SQL tools (`C3`/`C4`) behave in accuracy, token cost, and latency as business history grows.

**Commands executed:**
```zsh
../.venv/bin/python evaluation/extract_bundle.py data/dev/cafe_01_x4 --llm claude
../.venv/bin/python evaluation/extract_bundle.py data/dev/cafe_01_x16 --llm claude
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01_x4 --configs C0 C1 C2 C3 C4 --llm claude
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01_x16 --configs C0 C1 C2 C3 C4 --llm claude
```

#### 5A. Scaling Extraction Accuracy

| Bundle | Run ID | Calls (Failed) | Field Accuracy | Input Tokens | Output Tokens | Ungrounded |
| --- | --- | --- | --- | --- | --- | --- |
| `cafe_01_x4` | `20261119-000312-extract-cafe_01_x4-claude-haiku-5-5` | 81 (0) | **324/327 (99.1%)** | 164,402 | 39,191 | 0 |
| `cafe_01_x16` | `20261119-001329-extract-cafe_01_x16-claude-haiku-5-5` | 321 (0) | **1,284/1,287 (99.8%)** | 651,844 | 153,732 | 0 |

#### 5B. Paired Within-Conversation Scaling Curve (`cafe_01` `x1` → `x4` → `x16`, same 21 convs / 28 scored turns)

- `x1`: `20261118-223250-cafe_01-claude-haiku-5-5`
- `x4`: `20261119-001330-cafe_01_x4-claude-haiku-5-5`
- `x16`: `20261119-002636-cafe_01_x16-claude-haiku-5-5`

| Config | Turn Success (`x1` → `x4` → `x16`) | Conv Success (`x1` → `x4` → `x16`) | Mean Tokens (`x1` → `x4` → `x16`) | Median Latency (`x1` → `x4` → `x16`) | Over-Abstention (`x1` → `x4` → `x16`) | Recall (`x1` → `x4` → `x16`) |
| --- | --- | --- | --- | --- | --- | --- |
| `C0` | 20/28 (71%) → 22/28 (79%) → 21/28 (75%) | 14/21 → 17/21 → 16/21 | 7,872 → 19,061 → **62,973** | 6.85s → 7.31s → **8.91s** | 0% → 0% → 0% | 1.000 → 1.000 → 1.000 |
| `C1` | 14/28 (50%) → 11/28 (39%) → **9/28 (32%)** | 8/21 → 6/21 → 6/21 | 5,004 → 4,648 → 4,618 | 5.86s → 5.21s → 5.02s | 33% → 44% → **56%** | 0.636 → 0.364 → **0.341** |
| `C2` | 15/28 (54%) → 6/28 (21%) → **7/28 (25%)** | 10/21 → 4/21 → 4/21 | 4,709 → 4,300 → 4,318 | 5.76s → 5.24s → 5.73s | 17% → **56%** → **56%** | 0.705 → 0.318 → **0.273** |
| **`C3`** | 22/28 (79%) → **24/28 (86%)** → 21/28 (75%) | 17/21 → 18/21 → 16/21 | 11,019 → 13,743 → **17,053** | 4.78s → 5.11s → **5.02s** | **0% → 0% → 0%** | 0.810 → 0.818 → 0.795 |
| **`C4`** | 22/28 (79%) → 23/28 (82%) → 20/28 (71%) | 16/21 → 17/21 → 16/21 | 11,501 → 13,885 → 18,594 | 4.71s → 5.60s → 5.15s | **0% → 0% → 0%** | 0.900 → 0.864 → 0.881 |

**Key findings:**
- **BM25 (`C1`/`C2`) collapses under scale:** Turn success falls to `32%` (`C1`) and `25%` (`C2`) at `x16`, with over-abstention reaching `56%` and recall falling below `0.35`.
- **`C3` preserves accuracy with massive efficiency advantages over `C0`:** `C3` stays at `75%`–`86%` (`28/28` parsed at `x4` and `x16`, `0%` unwarranted warnings, `0%` over-abstention). At `x16`, `C0`'s token consumption explodes **8.0×** (`7,872 → 62,973`), while `C3` grows only **1.5×** (`11,019 → 17,053` — **3.7× fewer tokens** and **1.8× faster** than `C0`).

---

### Prompt 6 — Frozen `v2` Held-Out Evaluation (`data/test/landscaping_01`)

**Why it was run:**  
`data/test/landscaping_01` (30 conversations, 40 scored turns) was frozen before any evaluation run and never used for prompt, threshold, or tool tuning. Running it once after all `v2` development and safety gates passed tests out-of-sample generalization on an unseen business (note: generated with the same PDF templates as the development bundles).

**Commands executed:**
```zsh
../.venv/bin/python evaluation/extract_bundle.py data/test/landscaping_01 --llm claude
../.venv/bin/python evaluation/run_eval.py data/test/landscaping_01 --configs C0 C1 C2 C3 C4 --llm claude
```

**Exact results (`20261119-010517-landscaping_01-claude-haiku-5-5` — 30 convs, 40 scored turns; reported directly from terminal output without inspecting held-out files):**

| Config | Turn Success | Conversation Success | Answer Type | Exact Values | Parsed | Median Latency (s) | Mean Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `C0` | 25/40 (62%) | 17/30 | 78% | 84% | 38/40 | 6.64 | 9,470 |
| `C1` | 16/40 (40%) | 12/30 | 68% | 66% | 39/40 | 5.92 | 5,136 |
| `C2` | 20/40 (50%) | 13/30 | 65% | 78% | 39/40 | 5.32 | 4,862 |
| **`C3`** | **29/40 (72%)** | **21/30** | **85%** | 82% | 39/40 | 5.29 | 12,900 |
| **`C4`** | 27/40 (68%) | 20/30 | 82% | 80% | 39/40 | 5.26 | 12,684 |

**Key findings:**  
`C3` (`72%` turn success, `21/30` conversations) is the top-performing configuration on the frozen held-out test bundle, leading `C0` by **+10 points**, `C2` by **+22 points**, and `C1` by **+32 points**, while running faster than `C0` (`5.29s` vs `6.64s`) and matching oracle `C4` (`68%`).

---

### Prompt 7 — Offline Paired Statistical Inference (`evaluation/stats.py`)

**Why it was run:**  
Computes two-sided exact McNemar tests and 10,000-resample `(scenario, query_id)`-clustered bootstrap 95% confidence intervals (seed 259) separately for each stratum. Because each stratum contains **1 run per scenario**, there is zero repeat-inflation in the exact McNemar `p`-values.

**Commands executed:**
```zsh
../.venv/bin/python evaluation/stats.py evaluation/results/20261118-223250-cafe_01-claude-haiku-5-5 evaluation/results/20261118-224539-plumbing_01-claude-haiku-5-5
../.venv/bin/python evaluation/stats.py evaluation/results/20261118-231330-bakery_01-claude-haiku-5-5 evaluation/results/20261118-232652-clinic_01-claude-haiku-5-5
../.venv/bin/python evaluation/stats.py evaluation/results/20261119-010517-landscaping_01-claude-haiku-5-5
```

#### 7A. Core `v2` Dev (`cafe_01` + `plumbing_01` — 51 conversation clusters, 68 scored turns)

| Pair (A vs B) | Discordant (A:B) | Exact McNemar `p` | Diff (A − B) | 95% Bootstrap CI |
| --- | --- | --- | --- | --- |
| `C0 vs C1` | 21:3 | **0.000** | +26.5% | `[+12.7%, +40.6%]` |
| `C0 vs C2` | 13:6 | 0.167 | +10.3% | `[-2.9%, +23.3%]` |
| `C0 vs C3` | 4:11 | 0.118 | -10.3% | `[-22.0%, +0.0%]` |
| `C0 vs C4` | 4:13 | **0.049** | -13.2% | `[-25.4%, -1.6%]` |
| `C1 vs C2` | 2:13 | **0.007** | -16.2% | `[-27.6%, -4.8%]` |
| `C1 vs C3` | 5:30 | **0.000** | **-36.8%** | `[-52.9%, -20.3%]` |
| `C1 vs C4` | 4:31 | **0.000** | **-39.7%** | `[-55.1%, -24.6%]` |
| `C2 vs C3` | 5:19 | **0.007** | **-20.6%** | `[-35.1%, -6.8%]` |
| `C2 vs C4` | 5:21 | **0.002** | **-23.5%** | `[-37.9%, -9.8%]` |
| `C3 vs C4` | 2:4 | 0.688 | -2.9% | `[-10.0%, +4.2%]` |

#### 7B. Expanded `v2` Dev (`bakery_01` + `clinic_01` — 36 conversation clusters, 53 scored turns)

| Pair (A vs B) | Discordant (A:B) | Exact McNemar `p` | Diff (A − B) | 95% Bootstrap CI |
| --- | --- | --- | --- | --- |
| `C0 vs C1` | 12:4 | 0.077 | +15.1% | `[+0.0%, +32.0%]` |
| `C0 vs C2` | 13:3 | **0.021** | +18.9% | `[+3.9%, +35.4%]` |
| `C0 vs C3` | 13:6 | 0.167 | +13.2% | `[-1.9%, +28.3%]` |
| `C0 vs C4` | 12:6 | 0.238 | +11.3% | `[-2.1%, +25.4%]` |
| `C1 vs C2` | 7:5 | 0.774 | +3.8% | `[-9.6%, +16.4%]` |
| `C1 vs C3` | 12:13 | 1.000 | -1.9% | `[-20.4%, +15.7%]` |
| `C1 vs C4` | 12:14 | 0.845 | -3.8% | `[-24.0%, +14.5%]` |
| `C2 vs C3` | 12:15 | 0.701 | -5.7% | `[-23.9%, +12.2%]` |
| `C2 vs C4` | 12:16 | 0.572 | -7.5% | `[-26.9%, +10.3%]` |
| `C3 vs C4` | 2:3 | 1.000 | -1.9% | `[-10.4%, +6.0%]` |

#### 7C. Frozen `v2` Held-Out (`landscaping_01` — 30 conversation clusters, 40 scored turns)

| Pair (A vs B) | Discordant (A:B) | Exact McNemar `p` | Diff (A − B) | 95% Bootstrap CI |
| --- | --- | --- | --- | --- |
| `C0 vs C1` | 10:1 | **0.012** | +22.5% | `[+7.9%, +36.6%]` |
| `C0 vs C2` | 7:2 | 0.180 | +12.5% | `[-2.6%, +28.2%]` |
| `C0 vs C3` | 2:6 | 0.289 | -10.0% | `[-25.0%, +2.6%]` |
| `C0 vs C4` | 4:6 | 0.754 | -5.0% | `[-22.0%, +10.0%]` |
| `C1 vs C2` | 3:7 | 0.344 | -10.0% | `[-25.0%, +7.3%]` |
| `C1 vs C3` | 0:13 | **0.000** | **-32.5%** | `[-47.4%, -18.7%]` |
| `C1 vs C4` | 2:13 | **0.007** | **-27.5%** | `[-44.1%, -11.6%]` |
| `C2 vs C3` | 0:9 | **0.004** | **-22.5%** | `[-37.8%, -9.5%]` |
| `C2 vs C4` | 3:10 | 0.092 | -17.5% | `[-36.4%, +0.0%]` |
| `C3 vs C4` | 3:1 | 0.625 | +5.0% | `[-4.9%, +15.0%]` |

---

## 3. Summary of Supported Claims & Explicit Limitations

### Claims Strongly Supported by the `v2` Evidence
1. **`v2` dramatically reduced exaggerated safety without harming attack defense:** `C3` unwarranted warnings dropped from `23%` (`v1`) to `0%` on core dev (`0/53`) and `2%` on expanded dev (`1/42`), while maintaining `8/8 (100%)` benign utility, `19/19 (100%)` utility under attack, and `0/19 (0%)` ASR across both safety suites.
2. **Tools (`C3`) decisively beat BM25 retrieval (`C1` and `C2`) on both core dev and frozen held-out:** `C3` beat `C1` by `+36.8%` (`p < 0.001`) on core dev and `+32.5%` (`13:0`, `p < 0.001`) on held-out `landscaping_01`; `C3` beat `C2` by `+20.6%` (`p = 0.007`) on core dev and `+22.5%` (`9:0`, `p = 0.004`) on held-out.
3. **Extraction error does not degrade end-to-end tool performance (`C3 ≈ C4`):** Across core dev (`-2.9%`, `p = 0.688`), expanded dev (`-1.9%`, `p = 1.000`), and held-out (`+5.0%`, `p = 0.625`), `C3` matches oracle `C4`.
4. **Tools scale far more efficiently than full-context `C0` and far more accurately than BM25 (`C1`/`C2`):** At `16×` corpus scale (`cafe_01_x16`), `C1`/`C2` drop to `32%`/`25%` (`56%` over-abstention), while `C3` matches `C0` (`75%` vs `75%`) using **3.7× fewer tokens** (`17,053` vs `62,973`) and **1.8× lower median latency** (`5.02s` vs `8.91s`).

### Limitations & Where Claims Must Stay Conservative
- **`C3` vs. `C0` accuracy on standard bundles:** `C3` leads `C0` consistently by ~10 points on core dev (`+10.3%`, `p = 0.118`, CI `[+0.0%, +22.0%]`) and held-out (`+10.0%`, `p = 0.289`, CI `[-2.6%, +25.0%]`), which is directional rather than individually significant at `p < 0.05` on single-run sample sizes.
- **Deterministic tool blind spots exposed by `bakery_01` and `clinic_01`:** When scenarios require many-to-one lump-sum payment matching (`txn_6006`) or payment-detail comparison on duplicate invoice numbers across vendors (`INV-204`, `INV-902`), `C0` (`69.8%`) leads `C3` (`56.6%`; `+13.2%`, `p = 0.167`). Adding `bill_id` support to `compare_vendor_payment_details` and multi-invoice matching to `matching.py` are clear next engineering priorities.
- **Synthetic templates & human validation:** All end-to-end bundles (including frozen `landscaping_01`) are synthetic text-native PDFs rendered from shared templates, and `bakery_01`/`clinic_01` gold files have been checked via automated validators and assistant spot-checking rather than independent human adjudication.
- **Single model & run-to-run variance:** All `v2` runs use `claude-haiku-5-5` (1 pass per bundle) without a temperature parameter, so single-run scores carry small turn-to-turn stochastic variance.
