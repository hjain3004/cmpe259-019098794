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

## Open

- Answering model and version, to be pinned before 1 Nov.
- Project name: "CashBooks Assist" unless renamed before the 17 Nov presentation.
- Retriever: BM25 unless a dense retriever clearly wins on development bundles.
