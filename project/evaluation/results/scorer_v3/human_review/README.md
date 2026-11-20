# Blinded Human-Review Packet (`scorer_v3`)

Both blind CSVs hide configuration (`C0`–`C4`), run ID, and automated verdicts (`old_verdict`, `new_verdict`).
The separate key files (`key_verdict_changes.csv`, `key_unchanged_sample.csv`) must remain unopened until human review is finished.

- `blind_verdict_changes.csv`: **10** turns where verdicts changed under `scorer_v3`.
- `blind_unchanged_sample.csv`: **48** stratified unchanged turns (up to 4 per `(stratum, pass/fail)` bucket, seed `259`).

## Instructions for Human Reviewer
1. Open `blind_verdict_changes.csv` and `blind_unchanged_sample.csv` only.
2. For each row, enter `PASS` or `FAIL` in `human_verdict` based on whether `displayed_reply` accurately and safely answers `turn_text` given the bundle records.
3. Record any edge-case observations (e.g., entity-value swap, contradictory prose, defensible reply-type boundary) in `human_notes`.
4. Only after completing all rows, join by `sample_id` against the corresponding `key_*.csv` to compute scorer-vs-human agreement.
