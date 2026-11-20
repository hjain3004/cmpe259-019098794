# `scorer_v3_1` + `specs_v3_1` Runner & Rescorer Integration Report

**Scorer version:** `scorer_v3_1` (`code/src/cashbooks/scoring.py`)  
**Shared spec loader:** `code/src/cashbooks/eval_specs.py`  
**Versioned specs & manifest:** `evaluation/specs_v3_1/amount_semantics_overrides.yaml`, `evaluation/specs_v3_1/manifest.json`  

---

## 1. What Was Integrated

1. **Shared evaluation-spec loader & strict validator (`code/src/cashbooks/eval_specs.py`):**
   - Shared identically by `evaluation/run_eval.py` and `evaluation/rescore_v3_1.py`.
   - Resolves bundle-to-scenario mappings **only** via the explicit `bundle_to_scenario` table in `amount_semantics_overrides.yaml` (mapping `cafe_01`, `cafe_01_x4`/`x16`/`x32`/`x64`, and `cafe_01_ctrl_x4`/`x16`/`x32`/`x64` explicitly to `cafe_01`; unmapped bundle names raise `EvaluationSpecError` rather than stripping filename suffixes).
   - Validates every override before any turn runs: unknown query IDs, out-of-range or unscored turn indices, unknown value keys, invalid semantics kinds (outside `signed_money`, `txn_magnitude`, `non_money_number`), and mismatched base gold values all raise actionable `EvaluationSpecError`s.
2. **Opt-in `--eval-spec` flag in `evaluation/run_eval.py`:**
   - Omitting `--eval-spec` preserves legacy `strict_historical` behavior verbatim.
   - Passing `--eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml` activates `with_specs_v3_1` as the unambiguous primary verdict across `log.jsonl`, `course.csv`, `summary.json`, `summary.md`, and `metadata.json`.
   - Always writes `metadata.json` recording `scoring_policy`, `scorer_version`, `resolved_scenario`, `model_version`, `prompt_version`, `git_head`, `git_dirty`, and SHA-256 hashes of `scoring.py`, `postprocess.py`, `eval_specs.py`, `gold.yaml`, `queries.yaml`, and (when enabled) `eval_spec` + `eval_spec_manifest`.
3. **Unambiguous primary verdict in `evaluation/rescore_v3_1.py`:**
   - Supports `--policy with_specs` (writes to `evaluation/results/scorer_v3_1_with_specs/`) and `--policy strict_historical` (writes to `evaluation/results/scorer_v3_1_strict/`), keeping strict historical-policy results and with-specs results in separate output trees while preserving `evaluation/results/scorer_v3/` and `evaluation/results/scorer_v3_1/` untouched.
   - `log.jsonl`, `course.csv`, `summary.json`, `summary.md`, `metadata.json`, and downstream `stats.py` inputs all agree 100% on the selected primary verdict.
4. **Predeclared `Q13` corpus-sensitivity reporting (before any new model outputs):**
   - `Q13` gold is **not** silently altered.
   - `amount_semantics_overrides.yaml` and `manifest.json` explicitly declare `Q13` as corpus-sensitive on scaled café bundles (`cafe_01_x4`/`x16`/`x32`/`x64` and `cafe_01_ctrl_x4`/`x16`/`x32`/`x64`) because scaling prepends historical BeanWorks invoices.
   - Both `run_eval.py` and `rescore_v3_1.py` run all 28 turns and report three separate views in `metadata.json` and `summary.md`: all 28 turns, the predeclared 27-turn invariant-task subset (excluding `Q13`), and `Q13` separately with its historical-comparison limitation disclosed.

---

## 2. Exact Runner Commands for New Evaluations (Run from `project/`)

**Controlled scaling runs with `specs_v3_1` (opt-in):**
```zsh
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01 --configs C0 C1 C2 C3 C4 --llm claude --eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01_ctrl_x16 --configs C0 C1 C2 C3 C4 --llm claude --eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01_ctrl_x64 --configs C0 C1 C2 C3 C4 --llm claude --eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml
```

**Expanded dev (`clinic_01`) with `specs_v3_1`:**
```zsh
../.venv/bin/python evaluation/run_eval.py data/dev/clinic_01 --queries-file data/dev/clinic_01/queries.yaml --configs C0 C1 C2 C3 C4 --llm claude --eval-spec evaluation/specs_v3_1/amount_semantics_overrides.yaml
```

**Legacy `strict_historical` mode (omit `--eval-spec`):**
```zsh
../.venv/bin/python evaluation/run_eval.py data/dev/cafe_01 --configs C0 C1 C2 C3 C4 --llm claude
```

**Offline rescoring under each separated policy (zero API calls):**
```zsh
../.venv/bin/python evaluation/rescore_v3_1.py --policy with_specs
../.venv/bin/python evaluation/rescore_v3_1.py --policy strict_historical
```
