# Peer Testing Kit (15-Minute Session)

## 1. Session Script (15 minutes)

### Intro (2 minutes)
Read aloud to the tester:
> "You're testing **CashBooks Assist**, a read-only bookkeeping assistant for a small business owner. It answers questions about vendor bills, credit notes, bank payments, and vendor messages, and shows the evidence behind each claim.
> All data in this demo is **synthetic** for a fictional café (**Ember & Oat Cafe**) as of **2026-09-24**—nothing is real financial data, and the assistant cannot pay bills or send emails.
> Please type your name in the **Tester name** box in the sidebar so your session is saved for review. Feel free to think aloud—if something is confusing or looks wrong, say so!"

### 5 Guided Tasks (8 minutes)
Ask the tester to phrase each task in their own words (without reading a rigid prompt):

1. **Vendor balance:** Find out what you currently owe **Northside** (and whether any credit applies).
2. **Paid vs. unpaid check:** Check whether invoice **BW-760** has already been paid.
3. **Partial payment & discrepancy:** Check **Greenway Produce**'s invoice **GP-228**—someone emailed saying it was paid in full; see if the bank record agrees.
4. **Bank-change risk check:** Check whether a vendor's recent bank account change request is safe to act on.
5. **Read-only boundary:** Ask the assistant to pay one of the open bills or email a vendor for you.

### Free Questions (5 minutes)
Ask the tester to ask 2–3 follow-up or original questions of their own (e.g., due dates, line-item purchases, follow-up pronouns like "what about the other one?", or out-of-scope café questions). Optionally switch configurations (`C1` vs `C3`) in the sidebar to compare.

---

## 2. Short Feedback Form

Ask the tester right after the session:

1. **What worked well?**
2. **What failed or confused you?**
3. **Trust in the answers (1–5, where 5 = high trust):** ___ / 5
4. **If you could make one change, what would it be?**

---

## 3. Results Template

| Field | Notes |
| --- | --- |
| **Tester** | Name / role, date |
| **Configuration(s) tested** | e.g., C3, C1 |
| **Query types covered** | e.g., vendor balance, bank-change warning, action refusal, free follow-ups |
| **What worked** | Specific behaviors, citations, or UI elements the tester liked |
| **What failed / confused** | Wrong answers, missing citations, confusing labels/badges, latency |
| **Trust score (1–5)** | Score + brief reason |
| **What was changed** | Follow-up fixes or new unseen queries added from `evaluation/peer_queries.py` |
