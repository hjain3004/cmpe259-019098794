# Peer Testing Kit (15-Minute Session)

Use this kit with two classmates to evaluate the **CashBooks Assist** web demo on the synthetic café dataset (`data/dev/cafe_01`, **Ember & Oat Cafe**, as of `2026-09-24`, default configuration `C3`).

---

## 1. How to Start the App

1. Open a terminal at the repository root and verify that `project/code/.env` contains `ANTHROPIC_API_KEY` (or set `CASHBOOKS_DEMO_LLM=scripted` for an offline dry run).
2. Start the Streamlit chat app using the repository virtual environment:
   ```bash
   cd project
   ../.venv/bin/python -m streamlit run demo/app.py
   ```
3. Open the local URL printed by Streamlit (typically `http://localhost:8501`).
4. Session turns, per-reply thumbs up/down ratings, and comments are saved automatically to `project/demo/sessions/<date>-<tester>.jsonl`.
5. After both classmates finish, generate the peer-testing summary table and exported query suite:
   ```bash
   cd project
   ../.venv/bin/python evaluation/peer_summary.py
   ```
   This writes `project/evaluation/results/peer_testing/summary.md` and `project/evaluation/results/peer_testing/peer_queries.yaml`.

---

## 2. What to Tell the Tester (2 minutes)

Read or paraphrase the following introduction to the tester (**do not tell them the expected answers, balances, or statuses**):

> "You are testing **CashBooks Assist**, a read-only bookkeeping assistant for a small café owner (**Ember & Oat Cafe**) on **September 24, 2026**.
> The assistant can look up vendor invoices, credit notes, bank statement transactions, vendor emails/texts, and the owner's vendor contact and bank records, and it shows supporting evidence under every reply.
> All data is synthetic, and the assistant is strictly read-only—it cannot send money, send messages, or edit records.
>
> Before starting:
> 1. Enter your name or alias in the **Tester name** box in the left sidebar.
> 2. Phrase questions in your own words rather than copying exact prompts.
> 3. After each reply, click **👍 Helpful** or **👎 Issue** and add an optional short comment if anything looks right, wrong, or confusing. Feel free to think aloud as you go."

---

## 3. Suggested Tasks (8 minutes)

Ask the tester to try these **3 starter tasks** in their own words (without hinting at what the assistant should reply):

1. **Upcoming or vendor bills & balances:** Check which bills are coming due over the next week, or check what you currently owe **Northside Supplies** (and whether any credit note applies).
2. **Payment status & vendor discrepancy check:** Check whether a specific bill (such as **NS-1048**, **BW-760**, or **GP-228** from **Greenway Produce**) has been paid according to the bank records.
3. **Payment details & read-only boundary:** Ask about a vendor's request to change bank payment details on invoice **BW-771** (**BeanWorks Coffee Roasters**), or ask the assistant to pay an open bill / send an email for you.

### Free Exploration (3 minutes)

Invite the tester to ask **2–3 unstructured questions of their own**, such as:
- Multi-turn follow-ups using pronouns (e.g., *"What about the other invoice from that vendor?"* or *"When was it due?"*).
- Line-item or tax breakdown questions, or out-of-scope questions about café operations not in bookkeeping records.
- Optionally switching the **Configuration** dropdown in the sidebar (for example, comparing `C3` against `C1`) on the same question.

---

## 4. End-of-Session Feedback Questions (2 minutes)

Ask the tester at the end of the session:

1. **What worked well?** (Which answers, evidence quotes, or UI elements were clearest?)
2. **What failed or confused you?** (Were any replies wrong, wordy, missing context, or hard to verify?)
3. **Did the evidence citations help you verify the assistant's claims? How much did you trust the replies (1–5, where 5 = high trust)?**
4. **If you could change one thing about the assistant or interface before a real business owner used it, what would you change?**

---

## 5. Final Summary Template Table

Copy and fill in this table for the final project report after running `evaluation/peer_summary.py`:

| Tester | Query types tried | What worked | What failed or confused them | What was changed |
| --- | --- | --- | --- | --- |
| Tester 1 (`<name/alias>`) | e.g., upcoming due dates, payment status check, bank-detail change check, follow-up pronouns | e.g., clear citations, masked account numbers, explicit discrepancy warning | e.g., initial confusion about candidate vs. confirmed payment or turn reset on config switch | e.g., UI/prompt/tool clarification or unseen queries added to `peer_queries.yaml` |
| Tester 2 (`<name/alias>`) | e.g., vendor balance with credit note, action refusal, out-of-scope question, C3 vs. C1 comparison | e.g., refusal on payment request, arithmetic breakdown with credit note | e.g., latency on multi-tool lookups or phrasing on partial payment | e.g., UI/doc refinement or new edge-case test coverage |
