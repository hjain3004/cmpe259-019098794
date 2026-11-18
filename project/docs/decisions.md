# Decision log

Every change from the submitted proposal ([`../proposal/proposal.pdf`](../proposal/proposal.pdf), 11 Sep 2026) or from the frozen plan ([`design.md`](design.md)) is recorded here with its date and reason. Once the test set is frozen, any change made after seeing test output is logged here and the full suite is rerun.

## 2026-10-16

**D1. Q29 and Q30 restored to the query set.**
The submitted proposal PDF lists 28 draft queries; two of the planned 30 dropped out during editing. They are restored in `evaluation/queries.yaml`:
- Q29, "How many coffee bags do I have in stock right now?" (expected ABSTAIN: stock on hand cannot be known from invoices).
- Q30, "What was the $1,750 payment on my bank statement for?" (expected ABSTAIN with the transaction facts: no bill matches).

Both test abstention, which the other 28 queries cover only lightly.

**D2. The oracle run is called C4 everywhere.**
Section 5 of the proposal calls it C4 and Section 9 calls it the "oracle diagnostic". All code, logs and reports use C4.

**D3. One sentence in Section 1 of the proposal is withdrawn.**
"The owner has to verify whether the names, receipts are genuine or not" contradicts Section 7, which puts forgery detection out of scope. The project's position is Section 7's: the assistant flags inconsistency against the owner's trusted vendor record and recommends independent verification; it does not judge whether a document is genuine.

**D4. Q17, turn 1 expects CLARIFY instead of ANSWER.**
The scenario holds two Greenway bills, so "Did I pay the Greenway bill?" is ambiguous. A correct assistant asks which bill is meant, and "the one before that" in turn 2 then resolves against the two bills it listed.

**D5. Q21 gains an unscored setup turn.**
"Was the second invoice paid?" needs a list for "second" to refer to. The conversation now opens with "List my Northside bills from this summer." That turn is marked `scored: false`; the two original turns are scored as before.

**D6. Q22, turn 3 expects WARN.**
"Could it be a typo?" asks about the intent behind a changed payment detail. The records cannot show intent, so the correct reply states the discrepancy and recommends confirming through the contact on file, which the contract treats as WARN.

**D7. Response contract made stricter than the design draft.**
The 14 Oct draft listed `evidence` as plain IDs and `calculation` as a string. The implemented contract (`code/src/cashbooks/contracts/response.py`) uses:
- evidence entries that pair an ID with the claim it supports, so citation validity can be scored per claim;
- a structured calculation with steps and a typed `Money` result;
- a `risk_indicators` field, required for WARN, so a warning must name what it warns about.

Validation rules: CLARIFY carries exactly one question; ANSWER and WARN cite at least one record; ABSTAIN carries no calculated result; unknown keys are rejected.

**D8. Extraction returns strings and quotes only.**
The extraction model returns each value as printed, with its verbatim source quote and page. Code converts money to `Decimal`, dates to ISO dates, and payment terms to derived due dates. This keeps arithmetic and date logic out of the extraction model and makes every stored value traceable to text that code has checked.

**D9. Masking targets unbroken runs of six or more digits.**
Hyphenated numbers are left alone so ISO dates and phone numbers on file stay readable. The scenario generator prints account and routing numbers without separators, so all of them are caught.

**D10. Reference list verified.**
`docs/references.md` replaces the reading list in the 14 Oct draft. Changes from that list:
- AbstentionBench is NeurIPS 2025 Datasets and Benchmarks, not a preprint.
- ExtractBench refers to Ferguson et al. (arXiv:2602.12247).
- MINT and Razorpay's Vulcan are dropped, since neither supports a design choice.
- FinBalance is added as the closest prior work.
- Every motivation statistic is cited to its primary source.

**D11. Record contracts extended for the store.**
`Bill` gains `printed_vendor_name` and `remit_routing_hash`; `VendorFingerprint` gains `routing_hash`; `Credit` gains `issued_on`, so a credit counts only from the date it was issued. `Bill.due_date` is the printed due date when there is one, otherwise the date derived from the terms. A bill is overdue only when unpaid or partly paid and its due date is strictly before the as-of date.

**D12. Stored quotes never contain full account numbers.**
Evidence spans and message bodies are stored with every run of six or more digits masked to the last four, keeping the original length so character offsets stay valid. Account and routing numbers themselves are kept only as keyed hashes plus last four digits.

**D13. Short vendor names resolve as candidates.**
Owners say "Greenway" or "Northside". A query whose words all match the start of a vendor's name or alias is treated as a candidate (score 0.9). When more than one vendor qualifies, every candidate is returned, so the caller can ask which one is meant.

**D14. Real invoices added for the extraction check.**
The end-to-end evaluation stays synthetic, because no public dataset links invoices, vendor messages, bank rows and a trusted vendor record with ground-truth payment links. To measure how much cleaner synthetic invoices are than real ones, the frozen extraction method is also scored on 40 real annotated invoices from DocILE, using DocILE's own text and field labels. DocILE files are not committed; only sample IDs and aggregate scores are.

## 2026-11-17

**D15. Changes made while building C1 to C4 on the café scenario.**
- `list_open_bills` gains `include_settled` (default false), because with only open bills the model could not see that NS-1031 was paid twice. `due_before` is inclusive.
- `match_payments` can now look up bank debits by amount and/or posted date, not only by invoice number or txn ID: an owner asks "what was the $842 payment on the 12th", not for a txn ID. Exactly one lookup mode per call. A confirmed result may list several links (one debit can be a duplicate of another).
- Payment matching uses ranked evidence: invoice number in the bank descriptor, then a unique full-amount match, then a unique duplicate of an already-paid total, then a unique partial payment. Without the ranking a full and a partial candidate competed and the Northside payments stayed unlinked.
- BM25 tokens add a whole-dollar variant for amounts ending in .00 ("$842" now matches "842.00"); recall@8 on the café questions went from 0.60 to 0.75. k = 8 was picked on the café scenario and is now frozen.
- Every configuration returns its JSON reply through the prompt and the same parser, not through a provider's JSON mode, because tool calling and JSON mode cannot be combined in one call for all configurations. This keeps the reply format identical across C1 to C4.
- Answering and extraction model: Google Gemini through the `google-genai` SDK, temperature 0. The default model string is set in `code/src/cashbooks/llm/gemini.py` and can be overridden with `LLM_MODEL`; every run logs the exact model string it used.
- Extraction: header fields and line items are separate calls; one call each per credit note and message. An empty string is read as "absent", and a value without a quote uses the value itself as the quote, which is then checked against the page like any other quote. Each call is made once and failures are logged, not retried.
- Scoring compares citations at document level (`span_inv_NS-1048_total` and `span_inv_NS-1048_p1` both count as `inv_NS-1048`), so C1's page chunks and C3's field spans are scored the same way.
- Fixed: the amount parser read "1728.00" (no thousands comma) as 172.00. Test cases added.

**D16. Answering and extraction model: Claude Haiku 5.5, not Gemini.**
The Gemini free tier allows 20 requests a day for the planned model, too few for one run, and the paid project had no credit. All four configurations and the extraction step now use `claude-haiku-5-5` through the Anthropic Messages API (`code/src/cashbooks/llm/claude.py`); the Gemini client is kept. One model answers every configuration; every log row records it. The current API takes no temperature setting, so runs are not bit-for-bit repeatable; differences of one or two turns between configurations are within run-to-run noise until repeated runs are reported. The system prompt and tool list are cached between calls to cut cost.

**D17. Two scoring fixes, applied to saved replies by `evaluation/rescore.py`.**
- A reply wrapped in a single ```json code fence is now unwrapped before parsing, in every configuration; it is logged as `unwrapped_code_fence`. Anything else that is not bare JSON still counts as unparsed.
- Q30's expected amount is money, so it now carries its currency (`1750.00 USD`); without it the scorer required the literal "1750.00" and rejected "$1,750" in all four configurations.
Neither fix touches the prompts, the model or the replies. The original run files are kept next to the rescored ones.

**D18. Numeric dates are never read in a guessed order.**
The real-receipt check (626 SROIE receipts, `evaluation/real_docs_check.py`) showed that the old parser, which assumed US month-first order, turned 23% of real receipt dates into a wrong but valid date without any error, and rejected most of the rest. `normalize/dates.py` now takes the order a document uses (`MDY` or `DMY`), read from the vendor's record and then the business record (`date_order`, set to `MDY` for the café). When only one reading is a real date (25/12/2018) it is used; when both are and no order is known (05/03/2026), the value is flagged as ambiguous and left empty instead of guessed. The parser also reads the other printed forms the receipts use (28-01-18, 21 MARCH 2018, 02/JAN/2017, 20180304). Re-scored on the same saved extractions, no model calls: with the order unknown, no date is silently wrong and ambiguous ones are flagged; told the receipts are day-first, almost all dates come out right. The café extraction is unchanged (87/87 fields with the reference extractor).

## Open

- Answering model: Gemini (D15); the exact model string is recorded in every run log.
- Project name: "CashBooks Assist" unless renamed before the 17 Nov presentation.
- Retriever: BM25 unless a dense retriever clearly wins on development bundles.
