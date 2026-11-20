# Corpus-Scaling Generator Validation (`x1`–`x64`, Ambiguity vs. Controlled Profiles)

## 1. Two Experimental Purposes & Profiles

Scaling `data/dev/cafe_01` supports two distinct experimental profiles in `data/generator/scale_bundle.py`:

1. **`ambiguity` profile (default; existing `cafe_01_x4`, `cafe_01_x16`, `cafe_01_x32`, `cafe_01_x64`) — Corpus Growth + Payment-Matching Uncertainty**
   - Keeps generic vendor bank descriptors without invoice numbers on added historical payments (`"NORTHSIDE SUP CO 8841"`, `"GREENWAY PRODUCE ACH"`, `"BEANWORKS COFFEE"`).
   - Preserved unchanged as **matching-ambiguity stress cases**. Because neither C3 (`extracted.sqlite`) nor C4 (`load_gold.py`, which deliberately uses the same `matching.py::link_payments` logic on clean fields) receives invoice references in those descriptors, scaling to `x32` and `x64` introduces amount-matching ambiguity alongside corpus growth.
2. **`controlled` profile (new `cafe_01_ctrl_x4`, `cafe_01_ctrl_x16`, `cafe_01_ctrl_x32`, `cafe_01_ctrl_x64`) — Controlled Corpus Volume**
   - Preserves all original target records (`cafe_01` invoices, credits, messages, bank rows, payments, vendors) verbatim, including original bank descriptors.
   - Appends explicit, accurate invoice references to generated background payment descriptors (`f"{vc['descriptor']} {num}"`, e.g., `"BEANWORKS COFFEE BW-500"`) so historical settlements are directly observable in `bank.csv`.
   - Allows the unchanged `link_payments` matcher (`matching.py` / `load_gold.py`) to confirm every added background payment without injecting ledger payment links into C4, isolating **corpus volume** from **payment-matching uncertainty**.

Both profiles reserve all existing identifiers (`invoice_number`, `txn_id`, `msg_id`, `credit_id`, `reference_or_po`) before allocation and guard `FORBIDDEN_AMOUNTS` with a `while` loop, preventing filename overwrites in `render.py` (`invoices/<invoice_number>.pdf`) and collisions such as `GP-221` / `GP-228` at `x64`.

## 2. Generator Version, Seed Provenance & Counts

- **Source bundle:** `data/dev/cafe_01` (`evaluation_clock = 2026-09-24`)
- **Generator script:** `data/generator/scale_bundle.py`
- **Generator SHA-256:** `59dd2b12dfb7dcf76b220ace5855757d12ff3fd3da3d4666051da7e8ec0ebe3e`
- **Seed:** `259`
- **Validator script:** `evaluation/validate_scaled_bundle.py`

| Profile | Bundle | Invoices | Credits | Messages | Bank rows | Payments | Vendors | Reproducibility note |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Base | `data/dev/cafe_01` | 8 | 1 | 4 | 15 | 5 | 3 | Source bundle |
| `ambiguity` | `data/dev/cafe_01_x4` | 32 | 1 | 16 | 69 | 29 | 3 | Preserved; matches generator `x4` byte-for-byte |
| `ambiguity` | `data/dev/cafe_01_x16` | 128 | 1 | 64 | 285 | 125 | 3 | Preserved; matches generator `x16` byte-for-byte |
| `ambiguity` | `data/dev/cafe_01_x32` | 256 | 1 | 128 | 573 | 253 | 3 | Preserved stress case |
| `ambiguity` | `data/dev/cafe_01_x64` | 512 | 1 | 256 | 1149 | 509 | 3 | Preserved stress case (`GP-221`/`GP-228` skipped) |
| `controlled` | `data/dev/cafe_01_ctrl_x4` | 32 | 1 | 16 | 69 | 29 | 3 | Explicit invoice refs on added debits |
| `controlled` | `data/dev/cafe_01_ctrl_x16` | 128 | 1 | 64 | 285 | 125 | 3 | Explicit invoice refs on added debits |
| `controlled` | `data/dev/cafe_01_ctrl_x32` | 256 | 1 | 128 | 573 | 253 | 3 | Explicit invoice refs on added debits |
| `controlled` | `data/dev/cafe_01_ctrl_x64` | 512 | 1 | 256 | 1149 | 509 | 3 | Explicit invoice refs on added debits (`GP-221`/`GP-228` skipped) |

No `extracted.sqlite` or `gold.sqlite` was written into any scaled bundle, and no extraction or model evaluation was run.

## 3. Matching-Ambiguity Stress Results & Observable Assignment Analysis (`cafe_01_x32`, `cafe_01_x64`)

Under the `ambiguity` profile, all ledger-truth checks (**Category A**) pass across `x4`–`x64`, while the unchanged deterministic matcher (`link_payments`) leaves **`6` paid historical bills unconfirmed at `x32`** (`v_beanworks: 6`) and **`27` paid historical bills unconfirmed at `x64`** (`v_beanworks: 22`, `v_northside: 3`, `v_greenway: 2`). In `load_gold` (`C4`) and extracted-record tools, those unconfirmed bills appear falsely open/overdue and alter `list_open_bills` (`x32`, `x64`) as well as Northside totals (`Q02`/`Q16`: `2318.57 USD` vs `1462.85 USD`, `Q19`: `855.72 USD` vs `0.00 USD`) and Greenway open bills (`Q17`: 4 bills vs 2) at `x64`.

Using **only observable documents** (`invoices` vendor/dates/totals and `bank.csv` descriptors/dates/amounts, without peeking at hidden `ledger["payments"]`), `evaluate_scaled_bundle.py::classify_observable_collisions` partitions those unconfirmed historical bills into three classes:

| Bundle | Unconfirmed total | Unique from local match | Unique only from joint assignment | Not identifiable from observable evidence |
| --- | ---: | ---: | ---: | ---: |
| `cafe_01_x32` | 6 | 0 | 0 | 6 (`BW-503/505`, `BW-516/517`, `BW-519/521`) |
| `cafe_01_x64` | 27 | 3 | 4 | 20 (10 symmetric pairs) |

Representative collision cases from `cafe_01_x64`:
1. **Unique from a local match (3 bills):** `GP-164` (`174.00` → `txn_1193` `GREENWAY PRODUCE ACH`), `GP-218` (`417.30` → `txn_1355` `GREENWAY PRODUCE ACH`), `NS-919` (`417.30` → `txn_1357` `NORTHSIDE SUP CO 8841`). Each debit names a distinct vendor and only one open bill of that vendor has that exact amount in `[issue_date, due_date + 45d]`, yet `matching.candidates_for_txn` blocks confirmation because its `open_same_amount` check ignores vendor boundaries.
2. **Unique only from joint assignment across transactions (4 bills):** `BW-560` (`174.00` → `txn_1182`), plus the `$216.00` BeanWorks chain `BW-624` (`[2026-03-16..2026-05-30]`) → `txn_1374` (`2026-03-22`), forcing `BW-591` (`[2026-01-07..2026-03-23]`) → `txn_1275` (`2026-01-19`), forcing `BW-573` (`[2025-12-01..2026-02-14]`) → `txn_1221` (`2025-12-11`). Each transaction sits inside two open BeanWorks windows locally, so greedy single-transaction matching cannot commit; global degree-1 peeling in the bipartite graph uniquely determines the assignment.
3. **Not identifiable from observable evidence (6 bills at `x32`, 20 bills at `x64`):** Pairs such as `NS-863` / `NS-866` (`219.21`, `[2025-11-08..2026-01-22]` & `[2025-11-15..2026-01-29]` with `txn_1189` `2025-11-16` & `txn_1198` `2025-11-23`) and `BW-519` / `BW-521` (`216.00`) form symmetric `K_{2,2}` components with identical vendors, amounts, descriptors, and overlapping date windows. Observable evidence proves both bills are settled as a pair, but permuting individual bill-to-transaction assignments leaves all observables unchanged.

## 4. Controlled-Profile Validation (`cafe_01_ctrl_x4`–`x64`)

All four controlled bundles (`cafe_01_ctrl_x4`, `cafe_01_ctrl_x16`, `cafe_01_ctrl_x32`, `cafe_01_ctrl_x64`) passed `evaluation/validate_scaled_bundle.py --strict-matcher`, separating **corpus-truth checks** from **unchanged-matcher tool-output checks**:

### A. Corpus-Truth Checks (`Category A`) — **PASS across `x4`, `x16`, `x32`, `x64`**
- Zero duplicate `invoice_number`, `(vendor_id, invoice_number)`, `txn_id`, `msg_id`, `credit_id`, `reference_or_po`, or document stems; all rendered PDFs (`32`, `128`, `256`, `512`) and `.fields.json` manifests verified on disk with zero overwrites.
- All original `cafe_01` records and `gold.yaml` preserved verbatim; `render.validate_ledger` and `data/generator/check_gold.py` pass with 0 errors.
- All added invoices, payment transactions, unrelated bank rows, and messages have dates `< 2026-07-01` (`paid >= issue_date`); zero added invoice totals or unlinked bank amounts intersect `FORBIDDEN_AMOUNTS`.

### B. Tool-Output Checks via Unchanged `load_gold` + `link_payments` (`Category B`) — **CLEAN across `x4`, `x16`, `x32`, `x64`**
- **`0` unconfirmed historical bills** (`false_open_historical_count = 0` at `x4`, `x16`, `x32`, `x64`); every historical invoice has exactly 1 `CONFIRMED` payment link and 0 `CANDIDATE` links.
- **`0` tool snapshot differences vs. `cafe_01`** across the café evaluation subset: `Q01` (`due_7d`: `[NS-1062]`), `Q02` (`1462.85 USD` Northside), `Q03` (overdue `[GP-221, GP-228]`), `Q04`/`Q08` (`NS-1048` `paid`, `842.00/777.85/64.15`), `Q06` (`GP-228` `212.30` if candidate applies), `Q07`/`Q12`/`Q18` (`BW-771` mismatch only), `Q09` (`txn_0193` confirmed for `NS-1048`), `Q10` (`NS-1031` only duplicate link), `Q11` (Northside verified alias), `Q14`/`Q15` (August coffee `486.00 USD`, `12` bags), `Q16` (`[NS-1062, NS-1070]`), `Q17` (`GP-221`/`GP-228`), `Q19` (`0.00 USD` Northside overdue), `Q30` (`txn_0205` unmatched).

### C. Remaining Changes in Historical Comparisons & Unverified Scope
Even when every added background invoice is cleanly settled, **paid status alone does not make every historical summary identical**:
- **BeanWorks historical range & count (`Q13`):** `BW-760` (`2026-08-04`, `486.00 USD`) stays the immediately preceding BeanWorks invoice and `BW-771` (`1962.00 USD`) remains far above every prior bill, but the set of settled BeanWorks invoices prior to `BW-771` grows from `1` (`486.00 USD`) in `cafe_01` to `9` (`180.00–486.00`) in `x4`, `41` (`126.00–525.00`) in `x16`, `83` (`108.00–525.00`) in `x32`, and `169` (`90.00–525.00`) in `x64`. Models citing "all previous BeanWorks invoices" or the historical range via `list_open_bills(..., include_settled=True)` will reflect those scale-dependent historical bounds.
- **Unverified without paid runs:** Live extraction (`extracted.sqlite`), C1/C2 BM25 ranking drift across 256/512 invoices, C0 full-corpus context length at `x32`/`x64`, and non-café scenarios (`Q21`–`Q28`) were not evaluated offline.
