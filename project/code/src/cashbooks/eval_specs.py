"""Shared loader, validator, and metadata helper for versioned evaluation specifications.

Shared identically by evaluation/run_eval.py and evaluation/rescore_v3_1.py so live
evaluations and offline rescoring apply the exact same amount-semantics overrides,
explicit bundle-to-scenario mappings, and provenance hashes.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.evaluation import LogRow, QuerySuite
from cashbooks.scoring import SCORER_VERSION

VALID_SEMANTIC_KINDS = frozenset({"signed_money", "txn_magnitude", "non_money_number"})
DEFAULT_POLICY = "strict_historical"


class EvaluationSpecError(ValueError):
    """Raised when an evaluation specification or override is invalid or unmapped."""


@dataclass(frozen=True)
class LoadedEvalSpec:
    spec_path: Path
    spec_version: str
    spec_sha256: str
    bundle_name: str
    resolved_scenario: str
    overrides_by_turn: dict[tuple[str, int], dict[str, dict[str, str]]] = field(default_factory=dict)
    corpus_sensitive_queries: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def policy_name(self) -> str:
        return f"with_{self.spec_version}"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state(cwd: Path) -> tuple[str, bool]:
    try:
        head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=cwd, text=True).strip())
        return head, dirty
    except Exception:
        return "unknown", True


def _gold_turns_for(gold: dict[str, Any], query_id: str) -> list[dict[str, Any]]:
    entry = gold[query_id]
    return list(entry.get("turns", []) if isinstance(entry, dict) else entry)


def load_eval_spec(
    spec_path: Path,
    bundle_name: str,
    suite: QuerySuite,
    gold: dict[str, Any],
) -> LoadedEvalSpec:
    """Load and strictly validate a versioned evaluation specification against suite and gold.

    Bundle-to-scenario resolution uses ONLY the explicit `bundle_to_scenario` mapping;
    unmapped bundle names raise EvaluationSpecError rather than stripping filename suffixes.
    """
    if not spec_path.exists():
        raise EvaluationSpecError(f"Evaluation spec file not found: {spec_path}")
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise EvaluationSpecError(f"Evaluation spec must be a YAML mapping: {spec_path}")

    spec_version = str(raw.get("version") or "").strip()
    if not spec_version:
        raise EvaluationSpecError(f"Evaluation spec missing required 'version': {spec_path}")

    bundle_map = raw.get("bundle_to_scenario")
    if not isinstance(bundle_map, dict) or not bundle_map:
        raise EvaluationSpecError(f"Evaluation spec missing explicit 'bundle_to_scenario' mapping: {spec_path}")
    if bundle_name not in bundle_map:
        raise EvaluationSpecError(
            f"Bundle {bundle_name!r} is not explicitly mapped in bundle_to_scenario of {spec_path}. "
            f"Add an explicit mapping instead of relying on suffix stripping."
        )
    resolved_scenario = str(bundle_map[bundle_name]).strip()
    if not resolved_scenario:
        raise EvaluationSpecError(f"Empty scenario mapping for bundle {bundle_name!r} in {spec_path}")

    suite_specs = {c.id: c for c in suite.conversations}
    all_overrides = raw.get("overrides") or {}
    if not isinstance(all_overrides, dict):
        raise EvaluationSpecError(f"'overrides' must be a mapping in {spec_path}")

    scenario_overrides = all_overrides.get(resolved_scenario) or {}
    if not isinstance(scenario_overrides, dict):
        raise EvaluationSpecError(f"overrides[{resolved_scenario!r}] must be a mapping in {spec_path}")

    overrides_by_turn: dict[tuple[str, int], dict[str, dict[str, str]]] = {}
    for qid, turns_map in scenario_overrides.items():
        if qid not in suite_specs:
            raise EvaluationSpecError(
                f"Override references unknown query {qid!r} not present in query suite (scenario {resolved_scenario!r})"
            )
        if qid not in gold:
            raise EvaluationSpecError(
                f"Override references query {qid!r} not present in gold.yaml (scenario {resolved_scenario!r})"
            )
        if not isinstance(turns_map, dict):
            raise EvaluationSpecError(f"Override turns for {qid!r} must be a mapping of turn_index -> keys")

        conv_spec = suite_specs[qid]
        gold_turns = _gold_turns_for(gold, qid)

        for raw_ti, key_map in turns_map.items():
            try:
                ti = int(raw_ti)
            except (TypeError, ValueError) as exc:
                raise EvaluationSpecError(f"Invalid turn index {raw_ti!r} for {qid!r}") from exc
            if ti < 0 or ti >= len(conv_spec.turns):
                raise EvaluationSpecError(
                    f"Override turn index {ti} out of range for {qid!r} (has {len(conv_spec.turns)} turn(s))"
                )
            if not conv_spec.turns[ti].scored:
                raise EvaluationSpecError(f"Override targets unscored setup turn {qid} t{ti}")

            gi = sum(1 for t in conv_spec.turns[:ti] if t.scored)
            if gi >= len(gold_turns):
                raise EvaluationSpecError(f"No gold turn entry for {qid} t{ti} (scored index {gi})")
            base_values = (gold_turns[gi] or {}).get("values") or {}
            if not isinstance(key_map, dict):
                raise EvaluationSpecError(f"Override value map for {qid} t{ti} must be a mapping")

            validated_keys: dict[str, dict[str, str]] = {}
            for vkey, vspec in key_map.items():
                if vkey not in base_values:
                    raise EvaluationSpecError(
                        f"Override references unknown value key {vkey!r} on {qid} t{ti} "
                        f"(available keys: {sorted(base_values)})"
                    )
                if not isinstance(vspec, dict):
                    raise EvaluationSpecError(
                        f"Override for {qid} t{ti}.{vkey} must be a mapping with 'kind' and 'value'"
                    )
                kind = str(vspec.get("kind") or "").strip().lower()
                if kind not in VALID_SEMANTIC_KINDS:
                    raise EvaluationSpecError(
                        f"Invalid amount semantics kind {kind!r} on {qid} t{ti}.{vkey}; "
                        f"expected one of {sorted(VALID_SEMANTIC_KINDS)}"
                    )
                if "value" not in vspec:
                    raise EvaluationSpecError(f"Override for {qid} t{ti}.{vkey} missing required 'value'")
                ovr_val = str(vspec["value"]).strip()
                base_val = str(base_values[vkey]).strip()
                if ovr_val != base_val:
                    raise EvaluationSpecError(
                        f"Incompatible base value on {qid} t{ti}.{vkey}: override has {ovr_val!r} "
                        f"but historical gold has {base_val!r}. Overrides may only declare amount semantics, "
                        f"not alter gold values."
                    )
                validated_keys[vkey] = {"kind": kind, "value": ovr_val}
            overrides_by_turn[(qid, ti)] = validated_keys

    # Collect predeclared corpus-sensitive queries applicable to this bundle
    cs_raw = raw.get("corpus_sensitive_queries") or {}
    corpus_sensitive: dict[str, dict[str, Any]] = {}
    if isinstance(cs_raw, dict):
        for qid, info in cs_raw.items():
            if not isinstance(info, dict):
                continue
            applies = list(info.get("applies_to_bundles") or [])
            if bundle_name in applies:
                if qid not in suite_specs or qid not in gold:
                    raise EvaluationSpecError(
                        f"corpus_sensitive_queries entry {qid!r} not present in suite/gold for bundle {bundle_name!r}"
                    )
                corpus_sensitive[qid] = {
                    "query_id": qid,
                    "reason": str(info.get("reason") or "").strip(),
                }

    return LoadedEvalSpec(
        spec_path=spec_path.resolve(),
        spec_version=spec_version,
        spec_sha256=sha256_file(spec_path),
        bundle_name=bundle_name,
        resolved_scenario=resolved_scenario,
        overrides_by_turn=overrides_by_turn,
        corpus_sensitive_queries=corpus_sensitive,
    )


def apply_turn_overrides(
    gold_values: dict[str, Any],
    loaded_spec: LoadedEvalSpec | None,
    query_id: str,
    turn_index: int,
) -> dict[str, Any]:
    """Return effective gold_values dict for one scored turn under the active policy."""
    out = dict(gold_values or {})
    if loaded_spec is None:
        return out
    turn_ovr = loaded_spec.overrides_by_turn.get((query_id, turn_index))
    if not turn_ovr:
        return out
    for k, spec in turn_ovr.items():
        out[k] = {"kind": spec["kind"], "value": spec["value"]}
    return out


def summarize_corpus_sensitive_split(
    rows: list[LogRow],
    excluded_query_ids: set[str],
) -> dict[str, Any]:
    """Report all turns, the predeclared invariant-task subset, and corpus-sensitive turns separately."""
    configs = list(dict.fromkeys(r.configuration for r in rows))
    out: dict[str, Any] = {
        "excluded_corpus_sensitive_queries": sorted(excluded_query_ids),
        "per_config": {},
    }
    for cfg in configs:
        crows = [r for r in rows if r.configuration == cfg]
        inv_rows = [r for r in crows if r.query_id not in excluded_query_ids]
        cs_rows = [r for r in crows if r.query_id in excluded_query_ids]
        out["per_config"][cfg] = {
            "all_turns": {
                "successes": sum(int(bool(r.success)) for r in crows),
                "turns": len(crows),
                "rate": round(sum(int(bool(r.success)) for r in crows) / (len(crows) or 1), 3),
            },
            "invariant_subset": {
                "successes": sum(int(bool(r.success)) for r in inv_rows),
                "turns": len(inv_rows),
                "rate": round(sum(int(bool(r.success)) for r in inv_rows) / (len(inv_rows) or 1), 3),
            },
            "corpus_sensitive_subset": {
                "successes": sum(int(bool(r.success)) for r in cs_rows),
                "turns": len(cs_rows),
                "rate": round(sum(int(bool(r.success)) for r in cs_rows) / (len(cs_rows) or 1), 3) if cs_rows else None,
            },
        }
    return out


def build_run_metadata(
    *,
    project_root: Path,
    run_id: str,
    bundle: Path,
    queries_path: Path,
    gold_path: Path,
    model_version: str,
    prompt_version: str,
    loaded_spec: LoadedEvalSpec | None,
    rows: list[LogRow],
) -> dict[str, Any]:
    """Build complete provenance metadata with SHA-256 hashes for a run."""
    repo_root = project_root.parent
    head, dirty = git_state(repo_root)
    hashes: dict[str, str] = {
        "scoring.py": sha256_file(project_root / "code" / "src" / "cashbooks" / "scoring.py"),
        "postprocess.py": sha256_file(project_root / "code" / "src" / "cashbooks" / "contracts" / "postprocess.py"),
        "eval_specs.py": sha256_file(Path(__file__).resolve()),
        "gold.yaml": sha256_file(gold_path),
        "queries.yaml": sha256_file(queries_path),
    }
    if loaded_spec is not None:
        hashes["eval_spec"] = loaded_spec.spec_sha256
        manifest_sibling = loaded_spec.spec_path.parent / "manifest.json"
        if manifest_sibling.exists():
            hashes["eval_spec_manifest"] = sha256_file(manifest_sibling)

    meta: dict[str, Any] = {
        "run_id": run_id,
        "bundle": str(bundle),
        "bundle_name": bundle.name,
        "resolved_scenario": loaded_spec.resolved_scenario if loaded_spec else bundle.name,
        "scoring_policy": loaded_spec.policy_name if loaded_spec else DEFAULT_POLICY,
        "scorer_version": SCORER_VERSION,
        "eval_spec_path": str(loaded_spec.spec_path) if loaded_spec else None,
        "eval_spec_version": loaded_spec.spec_version if loaded_spec else None,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "git_head": head,
        "git_dirty": dirty,
        "hashes": hashes,
    }
    if loaded_spec and loaded_spec.corpus_sensitive_queries:
        meta["corpus_sensitive_queries"] = loaded_spec.corpus_sensitive_queries
        meta["invariant_subset_summary"] = summarize_corpus_sensitive_split(
            rows, set(loaded_spec.corpus_sensitive_queries)
        )
    return meta
