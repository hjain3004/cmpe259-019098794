# References

Each entry says what it is used for in this project. **PR** = peer-reviewed; **Preprint** = arXiv only as of October 2026. BibTeX for the core list is in [`references.bib`](references.bib).

Venues and IDs were checked on 16 Oct 2026. Entries marked † come from standard bibliographic records and were not re-fetched; check their DOI or Anthology ID before the final report.

The checkboxes track reading status: `[x]` read, `[ ]` not yet.

## Core

### Retrieval (C0–C2)

- [x] Lewis, P. et al. **Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.** NeurIPS 2020. PR †. <https://arxiv.org/abs/2005.11401>
  The retrieve-then-generate paradigm that C1 instantiates.
- [x] Robertson, S. and Zaragoza, H. **The Probabilistic Relevance Framework: BM25 and Beyond.** Foundations and Trends in Information Retrieval 3(4), 2009. PR †. <https://doi.org/10.1561/1500000019>
  The C1 and C2 retriever.
- [ ] Liu, N. F. et al. **Lost in the Middle: How Language Models Use Long Contexts.** TACL 12, 2024. PR †. <https://arxiv.org/abs/2307.03172>
  The main risk for C2: records placed mid-context are used less reliably.
- [ ] Li, Z., Li, C., Zhang, M., Mei, Q. and Bendersky, M. **Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach.** EMNLP 2024 Industry Track, pp. 881–893. PR. <https://aclanthology.org/2024.emnlp-industry.66/>
  Explains why C0 (whole corpus in the prompt) ties the tools when the corpus fits.
- [ ] Jin, B., Yoon, J., Han, J. and Arık, S. Ö. **Long-Context LLMs Meet RAG: Overcoming Challenges for Long Inputs in RAG.** ICLR 2025. PR. <https://arxiv.org/abs/2410.05983>
  Hard negatives drive long-context degradation; basis for the planned corpus-scaling experiment.

### Structured data and tools (C2, C3)

- [x] Biswal, A., Patel, L., Jha, S., Kamsetty, A., Liu, S., Gonzalez, J. E., Guestrin, C. and Zaharia, M. **Text2SQL is Not Enough: Unifying AI and Databases with TAG.** CIDR 2025. PR. <https://vldb.org/cidrdb/papers/2025/p11-biswal.pdf>
  Retrieval alone handles point lookups but not aggregation and computation; the main argument for C3. C3 is described as TAG-inspired, not as TAG.
- [ ] Gao, L. et al. **PAL: Program-aided Language Models.** ICML 2023. PR †. <https://arxiv.org/abs/2211.10435>
  Offloading arithmetic and date logic to code, as `sum_amount_due` and the terms parser do.
- [ ] Yao, S., Shinn, N., Razavi, P. and Narasimhan, K. **τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains.** ICLR 2025. PR. <https://arxiv.org/abs/2406.12045>
  Template for evaluating multi-turn, rule-bound tool use with a user in the loop.

### Extraction and structured outputs (extraction gate)

- [x] Šimsa, Š. et al. **DocILE Benchmark for Document Information Localization and Extraction.** ICDAR 2023, LNCS, pp. 147–166. PR. <https://doi.org/10.1007/978-3-031-41679-8_9>
  Separate tasks for key information (header) and line items justify extracting them in separate calls.
- [x] Ferguson, N., Pennington, J., Beghian, N., Mohan, A., Kiela, D., Agrawal, S. and Nguyen, T. H. **ExtractBench: A Benchmark and Evaluation Methodology for Complex Structured Extraction.** 2026. Preprint. <https://arxiv.org/abs/2602.12247>
  Extraction validity degrades as schemas get broader (0% valid output on a 369-field financial schema). Cited as evidence for a shallow schema, not as a controlled causal result: the benchmark is small and schema breadth is confounded with document type. A different 2026 preprint shares the name (Zhang et al., arXiv:2607.29677); this project cites Ferguson et al.
- [x] Tam, Z. R. et al. **Let Me Speak Freely? A Study on the Impact of Format Restrictions on Large Language Model Performance.** EMNLP 2024 Industry Track. PR. <https://aclanthology.org/2024.emnlp-industry.91/>
  Format restrictions can hurt reasoning: the case against constrained decoding in the gate.
- [ ] Geng, S. et al. **JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models.** 2025. Preprint (v1 titled "Generating Structured Outputs from Language Models: Benchmark and Studies"). <https://arxiv.org/abs/2501.10868>
  Constrained decoding frameworks compared on compliance and coverage: the case for it.

### Financial QA and the closest prior work

- [x] Chen, Z. et al. **ConvFinQA: Exploring the Chain of Numerical Reasoning in Conversational Finance Question Answering.** EMNLP 2022. PR †. <https://arxiv.org/abs/2210.03849>
  Multi-turn numeric QA over financial documents; the nearest established task to follow-ups such as "and the one before that?".
- [x] Tumpati, S. et al. **FinBalance: A Multi-Document Accounting Reconciliation Benchmark.** 2026. Preprint; its repository reports acceptance to Findings of EMNLP 2026 (not yet confirmed in the ACL Anthology). <https://arxiv.org/abs/2606.15949>
  Generator-built, ledger-grounded document bundles with cited outputs; the closest neighbour. The paper reports best exact balance-sheet accuracy of at most 46%, and a 26–41 percentage-point gap across four models between the balance sheet a model reports and the one obtained by replaying its own entries through a ledger, supporting computing totals in code.

### Entity and temporal

- [ ] Wang, T. et al. **Match, Compare, or Select? An Investigation of Large Language Models for Entity Matching.** COLING 2025, pp. 96–109. PR. <https://aclanthology.org/2025.coling-main.8/>
  Selecting among candidate records beats pairwise yes/no matching; shapes how invoices are linked to the trusted vendor list.
- [ ] Peeters, R., Steiner, A. and Bizer, C. **Entity Matching using Large Language Models.** EDBT 2025. PR. <https://arxiv.org/abs/2310.11244>
  LLM baseline for vendor-alias matching.

### Dialogue, clarification and abstention

- [x] Kirichenko, P., Ibrahim, M., Chaudhuri, K. and Bell, S. J. **AbstentionBench: Reasoning LLMs Fail on Unanswerable Questions.** NeurIPS 2025 Datasets and Benchmarks. PR. <https://arxiv.org/abs/2506.09038>
  Abstention remains unsolved even for strong models; justifies scoring ANSWER, CLARIFY and ABSTAIN explicitly.
- [ ] Zhang, T. et al. **CLAMBER: A Benchmark of Identifying and Clarifying Ambiguous Information Needs in Large Language Models.** ACL 2024. PR. <https://aclanthology.org/2024.acl-long.578/>
  When an LLM should ask one clarifying question.
- [ ] Laban, P., Hayashi, H., Zhou, Y. and Neville, J. **LLMs Get Lost In Multi-Turn Conversation.** 2025. Preprint. <https://arxiv.org/abs/2505.06120>
  Reports a 39% average drop from single-turn to multi-turn underspecified conversations, mostly from unreliability and premature answers; explains C3's follow-up failures.

### Grounding and citations

- [x] Gao, T., Yen, H., Yu, J. and Chen, D. **Enabling Large Language Models to Generate Text with Citations (ALCE).** EMNLP 2023. PR †. <https://arxiv.org/abs/2305.14627>
  Citation recall and precision, adapted here to field-level citation validity and evidence coverage.

### Security and prompt injection

- [x] Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T. and Fritz, M. **Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection.** AISec 2023. PR. <https://doi.org/10.1145/3605764.3623985>
  The threat model for instructions hidden in invoice memos and vendor emails (S02).
- [x] Debenedetti, E., Zhang, J., Balunović, M., Beurer-Kellner, L., Fischer, M. and Tramèr, F. **AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.** NeurIPS 2024 Datasets and Benchmarks. PR. <https://arxiv.org/abs/2406.13352>
  Definitions of Benign Utility, Utility Under Attack and Attack Success Rate used for S01–S10.
- [x] Debenedetti, E. et al. **Defeating Prompt Injections by Design (CaMeL).** 2025. Preprint. <https://arxiv.org/abs/2503.18813>
  Separating trusted control flow from untrusted data, and what that costs in utility. Also discusses manipulated extracted values, so this project does not claim that problem is new.
- [ ] Röttger, P., Kirk, H. R., Vidgen, B., Attanasio, G., Bianchi, F. and Hovy, D. **XSTest: A Test Suite for Identifying Exaggerated Safety Behaviours in Large Language Models.** NAACL 2024. PR. <https://aclanthology.org/2024.naacl-long.301/>
  Defines "exaggerated safety" and provides the basis for the unwarranted-warning rate.

### Evaluation methodology

- [ ] Berg-Kirkpatrick, T., Burkett, D. and Klein, D. **An Empirical Investigation of Statistical Significance in NLP.** EMNLP-CoNLL 2012. PR. <https://aclanthology.org/D12-1091/>
- [ ] Dror, R., Baumer, G., Shlomov, S. and Reichart, R. **The Hitchhiker's Guide to Testing Statistical Significance in Natural Language Processing.** ACL 2018. PR. <https://aclanthology.org/P18-1128/>
  Together: the one paired bootstrap interval over conversations.
- [ ] Card, D., Henderson, P., Khandelwal, U., Jia, R., Mahowald, K. and Jurafsky, D. **With Little Power Comes Great Responsibility.** EMNLP 2020, pp. 9263–9274. PR. <https://aclanthology.org/2020.emnlp-main.745/>
  Planning test-set size and reporting the minimum detectable effect.
- [ ] Miller, E. **Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations.** 2024. Preprint. <https://arxiv.org/abs/2411.00640>
  Comparing two models and planning an evaluation; confidence intervals that account for turns grouped in conversations.
- [x] Gill, A., Ravichander, A. and Marasović, A. **What Has Been Lost with Synthetic Evaluation?** Findings of EMNLP 2025. PR. <https://aclanthology.org/2025.findings-emnlp.526/>
  Generated test sets can be valid yet too easy; reason for hand verification, contrast pairs and the separately written held-out business type.

### Textbook

- [x] Jurafsky, D. and Martin, J. H. **Speech and Language Processing**, 3rd ed. draft, 19 August 2026 release. <https://web.stanford.edu/~jurafsky/slp3/>
  Ch. 2 Words and Tokens (normalization, edit distance); Ch. 11 Information Retrieval and RAG; Ch. 21 Information Extraction: Relations, Events, and Time; Ch. 24 Coreference Resolution and Entity Linking; Ch. 26 Conversation and its Structure; Appendix K Frame-based Dialogue Systems. Chapter numbers changed between the January and August 2026 drafts, so always cite the draft date.

## Background, cited only if used

- Chen, Sizhe et al. **StruQ: Defending Against Prompt Injection with Structured Queries.** USENIX Security 2025. PR. <https://arxiv.org/abs/2402.06363> (instruction/data separation via fine-tuning; related work)
- Zou, W. et al. **PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models.** USENIX Security 2025. PR. <https://arxiv.org/abs/2402.07867> (poisoned documents steer RAG answers; relevant to C1)
- Patil, S. G. et al. **The Berkeley Function Calling Leaderboard (BFCL).** ICML 2025. PR. <https://proceedings.mlr.press/v267/patil25a.html>
- Chen, Zhiyu et al. **FinQA: A Dataset of Numerical Reasoning over Financial Data.** EMNLP 2021. PR †. <https://arxiv.org/abs/2109.00122>
- Zhu, F. et al. **TAT-QA: A Question Answering Benchmark on a Hybrid of Tabular and Textual Content in Finance.** ACL 2021. PR †. <https://arxiv.org/abs/2105.07624>
- Rajpurkar, P., Jia, R. and Liang, P. **Know What You Don't Know: Unanswerable Questions for SQuAD.** ACL 2018. PR †. <https://arxiv.org/abs/1806.03822>
- Aliannejadi, M. et al. **Asking Clarifying Questions in Open-Domain Information-Seeking Conversations.** SIGIR 2019. PR †. <https://arxiv.org/abs/1907.06554>
- Strötgen, J. and Gertz, M. **HeidelTime: High Quality Rule-Based Extraction and Normalization of Temporal Expressions.** SemEval 2010. PR †. <https://aclanthology.org/S10-1071/> (rule-based temporal normalization baseline)
- Wang, Z. et al. **VRDU: A Benchmark for Visually-rich Document Understanding.** KDD 2023. PR. <https://doi.org/10.1145/3580305.3599929>
- Ostroukhov, M. et al. **PRAGMA: Revolut Foundation Model.** 2026. Preprint. <https://arxiv.org/abs/2604.08649> (transaction-sequence model; introduction only)
- Shi, F., Chen, X., Misra, K., Scales, N., Dohan, D., Chi, E., Schärli, N. and Zhou, D. **Large Language Models Can Be Easily Distracted by Irrelevant Context.** ICML 2023. PR. <https://arxiv.org/abs/2302.00093>

Recent preprints on invoice-borne prompt injection, useful for the related-work paragraph: ARGUS (<https://arxiv.org/abs/2605.03378>) and A2AS (<https://arxiv.org/abs/2510.13825>).

Not cited: MINT (arXiv:2608.14198) and Razorpay's Vulcan announcement. Neither supports a design or evaluation choice in this project.

## Datasets

| Dataset | Use in this project | Link |
| --- | --- | --- |
| SROIE (ICDAR 2019) | Real-document extraction check: 626 receipts (transcripts only, MIT license; receipts, not supplier invoices) | <https://github.com/zzzDavid/ICDAR-2019-SROIE> |
| DocILE (annotated set) | Planned for the real-invoice extraction check, but not used (replaced by SROIE) | <https://docile.rossum.ai/> · code: <https://github.com/rossumai/docile> |
| Synthetic scenario bundles | Everything else: reconciliation, dialogue, safety (generated in `data/generator/`) | this repository |

Considered and not used: CORD (receipts, not vendor invoices), PaySim and the Berka data (bank transactions with no linked documents), the Enron corpus (email with no linked invoices or bank rows). None links documents, messages and bank rows for one business.

## Motivation statistics (introduction only)

Cite the primary source for every number.

| Figure | Source |
| --- | --- |
| Business email compromise losses of about $3.05B across 24,768 complaints in 2025 | FBI IC3, *2025 Internet Crime Report* (April 2026). Confirm exact figures against the ic3.gov PDF before citing. |
| 74% of surveyed organizations affected by BEC in 2025 (465 US treasury practitioners; mostly mid-size and large firms) | AFP, *2026 Payments Fraud and Control Survey* (April 2026) |
| Imposter scams the most-reported fraud category; nearly $1B lost to business impersonators in 2025 (consumer reports) | FTC Consumer Sentinel Network data, press release of 15 June 2026 |
| US fraud losses could reach $40B by 2027 from $12.3B in 2023 | Deloitte Center for Financial Services. This is a scenario forecast for generative-AI-enabled fraud, not a measured loss. |

MIT Technology Review Insights, *Battling Next-Gen Financial Fraud* (2025), is sponsored by Plaid. It may be cited once as industry framing, but not as the source of any number.
