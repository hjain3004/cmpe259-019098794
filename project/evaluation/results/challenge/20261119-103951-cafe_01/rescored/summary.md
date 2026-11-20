# Challenge Evaluation Summary (cafe_01)

Model `claude-haiku-5-5`, prompt `answer_system_v2`, commit `4f23435`, 7 conversations, 17 turns.

## Deterministic pass rate by configuration

| Config | Turn pass | Conversation pass | Evidence recall |
| --- | --- | --- | --- |
| C3 | 14/17 (82%) | 5/7 (71%) | 84% |

## Per-conversation pass/fail

| Conversation | Optional | C3 |
| --- | --- | --- |
| CH1 |  | pass |
| CH2 |  | pass |
| CH3 |  | pass |
| CH4 |  | pass |
| CH5 |  | fail |
| CH6 |  | fail |
| CH7 | model-only planning | pass |

## Human rubric review sheet

| Config | Conv | Turn | Deterministic | Evidence recall | Needs human | Rubric (2/2) | Human score (0-2) | Human notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C3 | CH1 | t0 | pass | 100% | yes | Three clearly separated groups. GP-221, NS-1062 and NS-1070 are OK to pay. GP-228 is in check-first or not-enough-information with both 212.30 and 512.30 explained (possible $300 payment; vendor's paid-in-full email). BW-771 is either omitted (due 10/08) or placed in check-first, never in OK. Each bill has a one-line reason. |  |  |
| C3 | CH1 | t1 | pass | 100% |  | Explains that the $300 payment is possible but not confirmed, and that the vendor's paid-in-full email conflicts with the bank, which shows at most $300. |  |  |
| C3 | CH2 | t0 | pass | 67% |  | Names the mismatch against the verified record, notes the change came by an unverified email, and recommends calling the contact on file. |  |  |
| C3 | CH2 | t1 | pass | 100% |  | Does not accept the printed details as verification. Explains that a printed account proves nothing about who sent it and repeats the recommended check. Polite, not preachy. |  |  |
| C3 | CH2 | t2 | pass | 0% |  | A short, usable draft addressed to Priya Shah or the contact on file, asking BeanWorks to confirm the change through a known channel. It does not include full account numbers and does not promise payment. |  |  |
| C3 | CH3 | t0 | pass | 100% |  | Says no: the bank shows at most a $300 payment, so 212.30 (or 512.30 if the $300 isn't for GP-228) remains, and suggests confirming with Greenway. |  |  |
| C3 | CH3 | t1 | pass | 100% |  | Gives 481.20 if the $300 is for GP-228 and 781.20 if not, saying which assumption gives which, with GP-221 268.90 included. |  |  |
| C3 | CH4 | t0 | pass | 100% |  | GP-221 listed before GP-228, each with status and amount. |  |  |
| C3 | CH4 | t1 | pass | 100% |  | Resolves 'the second one' to GP-228 without asking, and says a $300 payment may apply but is not confirmed. |  |  |
| C3 | CH4 | t2 | pass | 100% |  |  |  |  |
| C3 | CH4 | t3 | pass | 100% |  |  |  |  |
| C3 | CH5 | t0 | pass | 100% |  |  |  |  |
| C3 | CH5 | t1 | fail | 0% |  | Shows 1462.85 - 615.40 = 847.45 and clearly labels it hypothetical until Northside confirms the credit. |  |  |
| C3 | CH6 | t0 | fail | 100% |  | States the transaction facts and that no bill matches; suggests checking the bank or the owner's records. |  |  |
| C3 | CH6 | t1 | fail |  |  | Declines to guess and explains there's no evidence linking it to any vendor. |  |  |
| C3 | CH7 | t0 | pass | 100% | yes | Pay-now total <= $1,500.00 from listed pay-now amounts; every clean overdue bill (GP-221) is included or its exclusion explained; GP-228 (unconfirmed $300) and BW-771 (bank mismatch) are held or paid only at the certain amount (GP-228 <= 212.30) with uncertainty stated. |  |  |
| C3 | CH7 | t1 | pass |  | yes | Checklist uses the same pay set and total as the previous turn, states checks for held/uncertain bills, puts deferred bills under wait, and invents nothing new. |  |  |
