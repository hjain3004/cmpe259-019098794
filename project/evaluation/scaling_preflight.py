"""Offline token, context-window, pricing-tier, and workload preflight for scaling.

    cd project
    ../.venv/bin/python evaluation/scaling_preflight.py \\
        data/dev/cafe_01 data/dev/cafe_01_ctrl_x16 data/dev/cafe_01_ctrl_x64 \\
        --profile controlled --configs C0 C3 \\
        --out-dir evaluation/results/scaling_preflight_ctrl_v3_1

All token and dollar figures are explicitly approximate LOCAL ESTIMATES (no offline
Anthropic tokenizer is installed; no API calls or network requests are made; dollar
ranges are estimates, NOT enforced spending caps). Uses Anthropic's documented
1,000,000-token context window for claude-haiku-5-5 (verified 2026-11-19) with a
configurable --context-limit deployment override, and models the 100,000-token
long-context pricing threshold (5x input/output/cache tier above 100k tokens).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

PROJECT = Path(__file__).resolve().parents[1]
CODE_SRC = PROJECT / "code" / "src"
DATA_GEN = PROJECT / "data" / "generator"
if str(CODE_SRC) not in sys.path:
    sys.path.insert(0, str(CODE_SRC))
if str(DATA_GEN) not in sys.path:
    sys.path.insert(0, str(DATA_GEN))

from cashbooks.configs.answer import K, MAX_TOOL_CALLS, system_prompt  # noqa: E402
from cashbooks.configs.retrieval import (  # noqa: E402
    BM25Retriever,
    build_raw_chunks,
    build_record_chunks,
    render_context,
)
from cashbooks.contracts.evaluation import QuerySuite  # noqa: E402
from cashbooks.contracts.tools import ListOpenBillsArgs, tool_definitions  # noqa: E402
from cashbooks.llm.base import simplify_schema  # noqa: E402
from cashbooks.llm.claude import DEFAULT_MODEL, MAX_TOKENS  # noqa: E402
from cashbooks.store.load_gold import load_gold  # noqa: E402
from cashbooks.tools.bills import list_open_bills  # noqa: E402
from scale_bundle import scale_ledger  # noqa: E402

# Official Anthropic documentation specs (retrieved 2026-11-19):
# - https://platform.claude.com/docs/en/models/haiku-5-5/overview
# - https://platform.claude.com/docs/en/about-claude/pricing
DOC_RETRIEVED_DATE = "2026-11-19"
MODEL_DOCS_URL = "https://platform.claude.com/docs/en/models/haiku-5-5/overview"
PRICING_DOCS_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
DOCUMENTED_CONTEXT_LIMIT = 1_000_000
LONG_CONTEXT_PRICING_THRESHOLD = 100_000

# Published USD per 1M tokens for claude-haiku-5-5 (<=100k vs >100k total input):
PRICING_USD_PER_1M = {
    "standard_le_100k": {"input": 0.10, "output": 0.50, "cache_write_5m": 0.125, "cache_read": 0.01},
    "long_gt_100k": {"input": 0.50, "output": 2.50, "cache_write_5m": 0.625, "cache_read": 0.05},
}

# Calibration constants anchored to cafe_01 x1/x4/x16 logs (approximate heuristic only):
PROSE_CHARS_PER_TOKEN = 3.6
STRUCTURED_CHARS_PER_TOKEN = 1.87
HIST_REPLY_CHARS_PER_TURN = 550

# Historical extraction call averages (cafe_01 x1=21, x4=81, x16=321):
APPROX_EXTRACT_IN_PER_CALL = 2030
APPROX_EXTRACT_OUT_PER_CALL = 480

# Retry / multi-round variance assumptions for high-bound sensitivity:
DEFAULT_HIGH_TOKEN_MARGIN = 1.25
DEFAULT_HIGH_RETRY_MULTIPLIER = 1.15  # +15% calls/tokens for transient API retries or extra C3 rounds
DEFAULT_HIGH_CACHE_WRITE_FRAC = 0.50

CONTROLLED_CANDIDATES = (
    "data/dev/cafe_01",
    "data/dev/cafe_01_ctrl_x16",
    "data/dev/cafe_01_ctrl_x64",
)
AMBIGUITY_CANDIDATES = (
    "data/dev/cafe_01",
    "data/dev/cafe_01_x4",
    "data/dev/cafe_01_x16",
    "data/dev/cafe_01_x32",
    "data/dev/cafe_01_x64",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _detect_bundle_profile(bundle_dir: Path, explicit_profile: str) -> str:
    if explicit_profile in ("controlled", "ambiguity"):
        if bundle_dir.name == "cafe_01":
            return "baseline_x1"
        return explicit_profile
    name = bundle_dir.name
    if name == "cafe_01":
        return "baseline_x1"
    if "_ctrl_" in name:
        return "controlled"
    if "_x" in name:
        return "ambiguity"
    return "custom"


def _inspect_sqlite_status(bundle_dir: Path) -> dict[str, Any]:
    db_path = bundle_dir / "extracted.sqlite"
    if not db_path.is_file():
        return {"present": False}
    conn = sqlite3.connect(str(db_path))
    try:
        bills = conn.execute("SELECT COUNT(*) FROM bills").fetchone()[0]
        claims = conn.execute("SELECT COUNT(*) FROM message_claims").fetchone()[0]
        bank_rows = conn.execute("SELECT COUNT(*) FROM bank_txns").fetchone()[0]
        links = conn.execute("SELECT COUNT(*) FROM payment_links").fetchone()[0]
    finally:
        conn.close()
    return {
        "present": True,
        "sha256": _sha256(db_path),
        "bills": bills,
        "message_claims": claims,
        "bank_txns": bank_rows,
        "payment_links": links,
    }


def _approx_tokens(prose_chars: int, structured_chars: int) -> int:
    return int(round(prose_chars / PROSE_CHARS_PER_TOKEN + structured_chars / STRUCTURED_CHARS_PER_TOKEN))


def _naive_div4_tokens(total_chars: int) -> int:
    return total_chars // 4


def _tokenizer_status() -> str:
    has_tiktoken = importlib.util.find_spec("tiktoken") is not None
    has_transformers = importlib.util.find_spec("transformers") is not None
    if has_tiktoken or has_transformers:
        return "approximate (third-party tokenizer present, not Anthropic Claude tokenizer)"
    return "approximate (character/table heuristic; no local Anthropic tokenizer installed)"


def _measure_queries(queries_path: Path, gold: dict[str, Any]) -> dict[str, Any]:
    suite = QuerySuite.model_validate(yaml.safe_load(queries_path.read_text(encoding="utf-8")))
    convs = [c for c in suite.conversations if c.id in gold]
    scored_turns = sum(1 for c in convs for t in c.turns if t.scored)
    q13_turns = sum(1 for c in convs if c.id == "Q13" for t in c.turns if t.scored)
    max_turns_in_conv = max((len(c.turns) for c in convs), default=1)
    max_q_chars = max((len(t.text) for c in convs for t in c.turns), default=80)
    return {
        "conversations": len(convs),
        "scored_turns": scored_turns,
        "invariant_subset_turns": scored_turns - q13_turns,
        "q13_turns": q13_turns,
        "max_turns_in_conv": max_turns_in_conv,
        "max_question_chars": max_q_chars,
    }


def _estimate_cost_usd_range(
    *,
    single_req_input: int,
    prefix_tokens_cached: int,
    uncached_new_tokens: int,
    output_tokens: int,
    total_calls: int,
    long_threshold: int,
    high_token_margin: float = DEFAULT_HIGH_TOKEN_MARGIN,
    high_retry_multiplier: float = DEFAULT_HIGH_RETRY_MULTIPLIER,
) -> dict[str, Any]:
    """Return conservative (low, high) estimated USD for a single config or build step.

    Low assumes 5-min ephemeral cache hits on the prefix after call 1 (all later calls read
    from cache at 0.1x), nominal token estimates, and 1.0x calls (0 retries).
    High assumes 50% cache writes / 50% cache reads, high_token_margin (default 1.25x) on
    token size, and high_retry_multiplier (default 1.15x) for retries/extra tool rounds.
    """
    is_long_low = single_req_input > long_threshold
    is_long_high = int(single_req_input * high_token_margin) > long_threshold
    r_low = PRICING_USD_PER_1M["long_gt_100k" if is_long_low else "standard_le_100k"]
    r_high = PRICING_USD_PER_1M["long_gt_100k" if is_long_high else "standard_le_100k"]

    n_writes_low = min(1, total_calls)
    n_reads_low = max(0, total_calls - n_writes_low)
    low_usd = (
        (n_writes_low * prefix_tokens_cached * r_low["cache_write_5m"])
        + (n_reads_low * prefix_tokens_cached * r_low["cache_read"])
        + (total_calls * uncached_new_tokens * r_low["input"])
        + (output_tokens * r_low["output"])
    ) / 1_000_000.0

    # High: 50% cache write / 50% cache read + token margin + retry multiplier
    high_calls = max(total_calls, int(round(total_calls * high_retry_multiplier)))
    n_writes_high = max(1, int(round(high_calls * DEFAULT_HIGH_CACHE_WRITE_FRAC)))
    n_reads_high = max(0, high_calls - n_writes_high)
    high_usd = high_token_margin * (
        (n_writes_high * prefix_tokens_cached * r_high["cache_write_5m"])
        + (n_reads_high * prefix_tokens_cached * r_high["cache_read"])
        + (high_calls * uncached_new_tokens * r_high["input"])
        + (output_tokens * high_retry_multiplier * r_high["output"])
    ) / 1_000_000.0
    return {
        "range_usd": [round(low_usd, 4), round(high_usd, 4)],
        "low_calls": total_calls,
        "high_calls_with_retries": high_calls,
        "low_pricing_tier": "long_gt_100k" if is_long_low else "standard_le_100k",
        "high_pricing_tier": "long_gt_100k" if is_long_high else "standard_le_100k",
    }


def _compute_config_estimates(
    *,
    sys_no_tools_chars: int,
    sys_tools_chars: int,
    tools_schema_chars: int,
    c0_ctx_chars: int,
    c1_ctx_chars: int,
    c2_ctx_chars: int,
    c3_open_payload_chars: int,
    c3_settled_payload_chars: int,
    history_chars: int,
    scored_turns: int,
    context_limit: int,
    output_reserve: int,
    long_threshold: int,
) -> dict[str, dict[str, Any]]:
    def _feasibility(req_in: int) -> str:
        total = req_in + output_reserve
        if total > context_limit:
            return "ESTIMATED_INFEASIBLE"
        if total >= int(0.85 * context_limit):
            return "ESTIMATED_NEAR_LIMIT"
        return "ESTIMATED_FEASIBLE"

    sys_no_tool_tok = _approx_tokens(sys_no_tools_chars, 0)
    sys_tool_plus_schema_tok = _approx_tokens(sys_tools_chars, tools_schema_chars)

    c0_req_in = _approx_tokens(sys_no_tools_chars + history_chars, c0_ctx_chars)
    c0_naive = _naive_div4_tokens(sys_no_tools_chars + history_chars + c0_ctx_chars)
    c0_uncached = max(0, c0_req_in - sys_no_tool_tok)
    c0_cost = _estimate_cost_usd_range(
        single_req_input=c0_req_in,
        prefix_tokens_cached=sys_no_tool_tok,
        uncached_new_tokens=c0_uncached,
        output_tokens=1800 * scored_turns,
        total_calls=scored_turns,
        long_threshold=long_threshold,
    )

    c1_req_in = _approx_tokens(sys_no_tools_chars + history_chars, c1_ctx_chars)
    c1_cost = _estimate_cost_usd_range(
        single_req_input=c1_req_in,
        prefix_tokens_cached=sys_no_tool_tok,
        uncached_new_tokens=max(0, c1_req_in - sys_no_tool_tok),
        output_tokens=1200 * scored_turns,
        total_calls=scored_turns,
        long_threshold=long_threshold,
    )

    c2_req_in = _approx_tokens(sys_no_tools_chars + history_chars, c2_ctx_chars)
    c2_cost = _estimate_cost_usd_range(
        single_req_input=c2_req_in,
        prefix_tokens_cached=sys_no_tool_tok,
        uncached_new_tokens=max(0, c2_req_in - sys_no_tool_tok),
        output_tokens=1200 * scored_turns,
        total_calls=scored_turns,
        long_threshold=long_threshold,
    )

    # C3/C4: separate typical bounded query (open bills only) from sample unbounded
    # `include_settled=True` single-call and 2-round accumulated multi-call turn.
    # Not a verified upper bound because multi-step tool trajectories vary by query.
    c3_open_req = _approx_tokens(sys_tools_chars + history_chars, tools_schema_chars + c3_open_payload_chars)
    c3_settled_one_call_req = _approx_tokens(
        sys_tools_chars + history_chars,
        tools_schema_chars + c3_settled_payload_chars + 1600,
    )
    c3_open_multicall_sum = int(round(c3_open_req * 2.5))
    c3_settled_multicall_sum = int(round(c3_settled_one_call_req * 2.2))

    # Split 28 turns: ~24 standard turns (stay <=100k) + ~4 settled-history turns (Q10/Q11 style).
    n_std = max(0, scored_turns - 4)
    n_settled = min(4, scored_turns)
    c3_calls_per_turn = 2.6
    c3_std_cost = _estimate_cost_usd_range(
        single_req_input=c3_open_req,
        prefix_tokens_cached=sys_tool_plus_schema_tok,
        uncached_new_tokens=max(0, c3_open_req - sys_tool_plus_schema_tok),
        output_tokens=int(round(1100 * n_std)),
        total_calls=int(round(n_std * c3_calls_per_turn)),
        long_threshold=long_threshold,
    )
    c3_settled_cost = _estimate_cost_usd_range(
        single_req_input=c3_settled_one_call_req,
        prefix_tokens_cached=sys_tool_plus_schema_tok,
        uncached_new_tokens=max(0, c3_settled_one_call_req - sys_tool_plus_schema_tok),
        output_tokens=int(round(1450 * n_settled)),
        total_calls=int(round(n_settled * c3_calls_per_turn)),
        long_threshold=long_threshold,
    )
    c3_total_cost = [
        round(c3_std_cost["range_usd"][0] + c3_settled_cost["range_usd"][0], 4),
        round(c3_std_cost["range_usd"][1] + c3_settled_cost["range_usd"][1], 4),
    ]
    c3_mean_multicall = int(round((n_std * c3_open_multicall_sum + n_settled * c3_settled_multicall_sum) / max(1, scored_turns)))

    return {
        "C0": {
            "calls_per_turn": "1",
            "estimated_calls_nominal": c0_cost["low_calls"],
            "estimated_calls_high_with_retries": c0_cost["high_calls_with_retries"],
            "pricing_tier_low": c0_cost["low_pricing_tier"],
            "pricing_tier_high": c0_cost["high_pricing_tier"],
            "single_request_input_approx": c0_req_in,
            "single_request_input_naive_div4": c0_naive,
            "single_request_with_reserve_approx": c0_req_in + output_reserve,
            "crosses_100k_pricing_tier": c0_req_in > long_threshold,
            "estimated_feasibility": _feasibility(c0_req_in),
            "run_summed_input_approx": c0_req_in * scored_turns,
            "run_output_approx": 1800 * scored_turns,
            "est_answering_cost_usd_range": c0_cost["range_usd"],
        },
        "C1": {
            "calls_per_turn": "1",
            "estimated_calls_nominal": c1_cost["low_calls"],
            "estimated_calls_high_with_retries": c1_cost["high_calls_with_retries"],
            "single_request_input_approx": c1_req_in,
            "single_request_with_reserve_approx": c1_req_in + output_reserve,
            "crosses_100k_pricing_tier": c1_req_in > long_threshold,
            "estimated_feasibility": _feasibility(c1_req_in),
            "run_summed_input_approx": c1_req_in * scored_turns,
            "run_output_approx": 1200 * scored_turns,
            "est_answering_cost_usd_range": c1_cost["range_usd"],
        },
        "C2": {
            "calls_per_turn": "1",
            "estimated_calls_nominal": c2_cost["low_calls"],
            "estimated_calls_high_with_retries": c2_cost["high_calls_with_retries"],
            "single_request_input_approx": c2_req_in,
            "single_request_with_reserve_approx": c2_req_in + output_reserve,
            "crosses_100k_pricing_tier": c2_req_in > long_threshold,
            "estimated_feasibility": _feasibility(c2_req_in),
            "run_summed_input_approx": c2_req_in * scored_turns,
            "run_output_approx": 1200 * scored_turns,
            "est_answering_cost_usd_range": c2_cost["range_usd"],
        },
        "C3": {
            "calls_per_turn": f"1..{MAX_TOOL_CALLS + 1} (loop)",
            "estimated_calls_nominal": c3_std_cost["low_calls"] + c3_settled_cost["low_calls"],
            "estimated_calls_high_with_retries": (
                c3_std_cost["high_calls_with_retries"] + c3_settled_cost["high_calls_with_retries"]
            ),
            "standard_turns_count": n_std,
            "settled_history_turns_count": n_settled,
            "standard_turns_pricing_tier_low": c3_std_cost["low_pricing_tier"],
            "settled_turns_pricing_tier_low": c3_settled_cost["low_pricing_tier"],
            "settled_turns_pricing_tier_high": c3_settled_cost["high_pricing_tier"],
            "sample_open_only_request_input_approx": c3_open_req,
            "sample_include_settled_single_request_input_approx": c3_settled_one_call_req,
            "sample_include_settled_with_reserve_approx": c3_settled_one_call_req + output_reserve,
            "sample_open_multicall_sum_approx": c3_open_multicall_sum,
            "sample_include_settled_multicall_sum_approx": c3_settled_multicall_sum,
            "mean_multicall_sum_approx": c3_mean_multicall,
            "sample_settled_crosses_100k_pricing_tier": c3_settled_one_call_req > long_threshold,
            "typical_open_crosses_100k_pricing_tier": c3_open_req > long_threshold,
            "estimated_feasibility": _feasibility(c3_settled_one_call_req),
            "run_summed_input_approx": c3_mean_multicall * scored_turns,
            "run_output_approx": 1150 * scored_turns,
            "est_answering_cost_usd_range": c3_total_cost,
            "payload_bound_disclaimer": "Sample observed/constructed payloads only; not a verified upper bound across arbitrary multi-call histories.",
        },
        "C4": {
            "calls_per_turn": f"1..{MAX_TOOL_CALLS + 1} (loop)",
            "estimated_calls_nominal": c3_std_cost["low_calls"] + c3_settled_cost["low_calls"],
            "estimated_calls_high_with_retries": (
                c3_std_cost["high_calls_with_retries"] + c3_settled_cost["high_calls_with_retries"]
            ),
            "sample_open_only_request_input_approx": c3_open_req,
            "sample_include_settled_single_request_input_approx": c3_settled_one_call_req,
            "sample_include_settled_with_reserve_approx": c3_settled_one_call_req + output_reserve,
            "sample_settled_crosses_100k_pricing_tier": c3_settled_one_call_req > long_threshold,
            "estimated_feasibility": _feasibility(c3_settled_one_call_req),
            "run_summed_input_approx": c3_mean_multicall * scored_turns,
            "run_output_approx": 1150 * scored_turns,
            "est_answering_cost_usd_range": c3_total_cost,
        },
    }


def _bundle_stats(
    bundle_dir: Path,
    queries_path: Path,
    context_limit: int,
    output_reserve: int,
    long_threshold: int,
    explicit_profile: str = "auto",
) -> dict[str, Any]:
    ledger = json.loads((bundle_dir / "ledger.json").read_text(encoding="utf-8"))
    gold = yaml.safe_load((bundle_dir / "gold.yaml").read_text(encoding="utf-8"))
    biz = ledger["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])
    q_stats = _measure_queries(queries_path, gold)

    sys_no_tools = system_prompt(biz["name"], as_of, tools=False)
    sys_tools = system_prompt(biz["name"], as_of, tools=True)
    tools_schema_json = json.dumps(
        [
            {"name": t["name"], "description": t["description"], "input_schema": simplify_schema(t["input_schema"])}
            for t in tool_definitions()
        ]
    )

    chunks = build_raw_chunks(bundle_dir)
    raw_ctx = render_context(chunks)
    retriever = BM25Retriever(chunks)
    top_k_ctx = render_context(retriever.chunks[:K])

    gold_store, _ = load_gold(bundle_dir)
    rec_chunks = build_record_chunks(gold_store, as_of)
    c2_top_k_chars = sum(len(f"[{c.chunk_id}] {c.source}\n{c.text}") for c in rec_chunks[:K])

    open_only = list_open_bills(gold_store, ListOpenBillsArgs(as_of=as_of, include_settled=False))
    all_settled = list_open_bills(gold_store, ListOpenBillsArgs(as_of=as_of, include_settled=True))
    open_json = open_only.model_dump_json()
    all_json = all_settled.model_dump_json()

    n_inv = len(ledger.get("invoices", []))
    n_cred = len(ledger.get("credits", []))
    n_msg = len(ledger.get("messages", []))
    n_bank = len(ledger.get("bank", []))
    est_extract_calls = 2 * n_inv + n_cred + n_msg

    # Extraction cost range (standard <=100k tier: ~2,030 in / ~480 out per call).
    # Each document call sends prompt schema + 1 page; system prompt cached after first call per schema.
    ext_in = est_extract_calls * APPROX_EXTRACT_IN_PER_CALL
    ext_out = est_extract_calls * APPROX_EXTRACT_OUT_PER_CALL
    ext_cost = _estimate_cost_usd_range(
        single_req_input=APPROX_EXTRACT_IN_PER_CALL,
        prefix_tokens_cached=900,
        uncached_new_tokens=max(0, APPROX_EXTRACT_IN_PER_CALL - 900),
        output_tokens=ext_out,
        total_calls=est_extract_calls,
        long_threshold=long_threshold,
    )

    sqlite_info = _inspect_sqlite_status(bundle_dir)
    profile = _detect_bundle_profile(bundle_dir, explicit_profile)
    # On baseline cafe_01 x1, extracted.sqlite already exists on disk cleanly; if reused, incremental extraction is $0.
    ext_required_if_reusing_x1 = 0 if (bundle_dir.name == "cafe_01" and sqlite_info["present"]) else est_extract_calls
    ext_cost_if_reusing_x1 = [0.0, 0.0] if ext_required_if_reusing_x1 == 0 else ext_cost["range_usd"]

    history_chars = (q_stats["max_turns_in_conv"] - 1) * (q_stats["max_question_chars"] + HIST_REPLY_CHARS_PER_TURN)
    state_block_chars = 350 if q_stats["max_turns_in_conv"] > 1 else 0

    configs = _compute_config_estimates(
        sys_no_tools_chars=len(sys_no_tools),
        sys_tools_chars=len(sys_tools),
        tools_schema_chars=len(tools_schema_json),
        c0_ctx_chars=len(raw_ctx),
        c1_ctx_chars=len(top_k_ctx),
        c2_ctx_chars=c2_top_k_chars,
        c3_open_payload_chars=len(open_json),
        c3_settled_payload_chars=len(all_json),
        history_chars=history_chars + state_block_chars + q_stats["max_question_chars"],
        scored_turns=q_stats["scored_turns"],
        context_limit=context_limit,
        output_reserve=output_reserve,
        long_threshold=long_threshold,
    )

    return {
        "label": bundle_dir.name,
        "profile": profile,
        "source": "on_disk",
        "bundle": str(bundle_dir),
        "has_extracted_sqlite": sqlite_info["present"],
        "extracted_sqlite_status": sqlite_info,
        "counts": {
            "invoices": n_inv,
            "credits": n_cred,
            "messages": n_msg,
            "bank_rows": n_bank,
            "raw_chunks": len(chunks),
            "gold_open_bills": len(open_only.bills),
            "gold_all_bills": len(all_settled.bills),
            "conversations": q_stats["conversations"],
            "scored_turns": q_stats["scored_turns"],
            "invariant_subset_turns": q_stats["invariant_subset_turns"],
            "q13_turns": q_stats["q13_turns"],
        },
        "raw_context_chars": len(raw_ctx),
        "open_bills_payload_chars": len(open_json),
        "all_bills_payload_chars": len(all_json),
        "extraction_estimate": {
            "estimated_calls_fresh": est_extract_calls,
            "estimated_calls_high_with_retries": ext_cost["high_calls_with_retries"],
            "approx_input_tokens_fresh": ext_in,
            "approx_output_tokens_fresh": ext_out,
            "est_cost_usd_range_fresh": ext_cost["range_usd"],
            "estimated_calls_if_reusing_compatible_x1": ext_required_if_reusing_x1,
            "est_cost_usd_range_if_reusing_compatible_x1": ext_cost_if_reusing_x1,
            "pricing_tier": ext_cost["low_pricing_tier"],
        },
        "configs": configs,
    }


def _project_scaled_stats(
    base_bundle: Path,
    factor: int,
    queries_path: Path,
    context_limit: int,
    output_reserve: int,
    long_threshold: int,
    seed: int = 259,
) -> dict[str, Any]:
    """Synthetic in-memory projection (kept strictly separate from on-disk bundles)."""
    base_led = json.loads((base_bundle / "ledger.json").read_text(encoding="utf-8"))
    gold = yaml.safe_load((base_bundle / "gold.yaml").read_text(encoding="utf-8"))
    q_stats = _measure_queries(queries_path, gold)

    scaled = scale_ledger(base_led, factor=factor, seed=seed)
    biz = scaled["business"]
    as_of = date.fromisoformat(biz["evaluation_clock"])
    sys_no_tools = system_prompt(biz["name"], as_of, tools=False)
    sys_tools = system_prompt(biz["name"], as_of, tools=True)
    tools_schema_json = json.dumps(
        [
            {"name": t["name"], "description": t["description"], "input_schema": simplify_schema(t["input_schema"])}
            for t in tool_definitions()
        ]
    )

    base_raw_chars = len(render_context(build_raw_chunks(base_bundle)))
    x16_dir = base_bundle.parent / f"{base_bundle.name}_ctrl_x16"
    if not x16_dir.is_dir():
        x16_dir = base_bundle.parent / f"{base_bundle.name}_x16"
    if x16_dir.is_dir():
        x16_raw_chars = len(render_context(build_raw_chunks(x16_dir)))
        per_x_chars = (x16_raw_chars - base_raw_chars) / 15.0
        est_raw_chars = int(round(base_raw_chars + (factor - 1) * per_x_chars))
    else:
        est_raw_chars = base_raw_chars * factor

    gold_store, _ = load_gold(base_bundle)
    open_only = list_open_bills(gold_store, ListOpenBillsArgs(as_of=as_of, include_settled=False)).model_dump_json()
    base_all = list_open_bills(gold_store, ListOpenBillsArgs(as_of=as_of, include_settled=True)).model_dump_json()
    if x16_dir.is_dir():
        x16_store, _ = load_gold(x16_dir)
        x16_all = list_open_bills(x16_store, ListOpenBillsArgs(as_of=as_of, include_settled=True)).model_dump_json()
        added_inv = max(1, len(x16_store.bills()) - len(base_led["invoices"]))
        marginal_inv_chars = (len(x16_all) - len(base_all)) / added_inv
        est_settled_chars = int(round(len(base_all) + (len(scaled["invoices"]) - len(base_led["invoices"])) * marginal_inv_chars))
    else:
        est_settled_chars = (len(base_all) // max(1, len(base_led["invoices"]))) * len(scaled["invoices"])

    n_inv = len(scaled.get("invoices", []))
    n_cred = len(scaled.get("credits", []))
    n_msg = len(scaled.get("messages", []))
    n_bank = len(scaled.get("bank", []))
    est_extract_calls = 2 * n_inv + n_cred + n_msg
    ext_in = est_extract_calls * APPROX_EXTRACT_IN_PER_CALL
    ext_out = est_extract_calls * APPROX_EXTRACT_OUT_PER_CALL
    ext_cost = _estimate_cost_usd_range(
        single_req_input=APPROX_EXTRACT_IN_PER_CALL,
        prefix_tokens_cached=900,
        uncached_new_tokens=max(0, APPROX_EXTRACT_IN_PER_CALL - 900),
        output_tokens=ext_out,
        total_calls=est_extract_calls,
        long_threshold=long_threshold,
    )
    history_chars = (q_stats["max_turns_in_conv"] - 1) * (q_stats["max_question_chars"] + HIST_REPLY_CHARS_PER_TURN)

    configs = _compute_config_estimates(
        sys_no_tools_chars=len(sys_no_tools),
        sys_tools_chars=len(sys_tools),
        tools_schema_chars=len(tools_schema_json),
        c0_ctx_chars=est_raw_chars,
        c1_ctx_chars=int(base_raw_chars * 0.45),
        c2_ctx_chars=3200,
        c3_open_payload_chars=len(open_only),
        c3_settled_payload_chars=est_settled_chars,
        history_chars=history_chars + 350 + q_stats["max_question_chars"],
        scored_turns=q_stats["scored_turns"],
        context_limit=context_limit,
        output_reserve=output_reserve,
        long_threshold=long_threshold,
    )

    return {
        "label": f"{base_bundle.name}_x{factor} (projected)",
        "profile": "projected",
        "source": "in_memory_projection",
        "bundle": str(base_bundle.parent / f"{base_bundle.name}_x{factor}"),
        "has_extracted_sqlite": False,
        "counts": {
            "invoices": n_inv,
            "credits": n_cred,
            "messages": n_msg,
            "bank_rows": n_bank,
            "raw_chunks": None,
            "conversations": q_stats["conversations"],
            "scored_turns": q_stats["scored_turns"],
            "invariant_subset_turns": q_stats["invariant_subset_turns"],
            "q13_turns": q_stats["q13_turns"],
        },
        "raw_context_chars": est_raw_chars,
        "extraction_estimate": {
            "estimated_calls_fresh": est_extract_calls,
            "estimated_calls_high_with_retries": ext_cost["high_calls_with_retries"],
            "approx_input_tokens_fresh": ext_in,
            "approx_output_tokens_fresh": ext_out,
            "est_cost_usd_range_fresh": ext_cost["range_usd"],
            "estimated_calls_if_reusing_compatible_x1": est_extract_calls,
            "est_cost_usd_range_if_reusing_compatible_x1": ext_cost["range_usd"],
            "pricing_tier": ext_cost["low_pricing_tier"],
        },
        "configs": configs,
    }


def _compute_totals(bundles: list[dict[str, Any]], selected_configs: list[str]) -> dict[str, Any]:
    fresh_ext_low = sum(b["extraction_estimate"]["est_cost_usd_range_fresh"][0] for b in bundles)
    fresh_ext_high = sum(b["extraction_estimate"]["est_cost_usd_range_fresh"][1] for b in bundles)
    reuse_ext_low = sum(b["extraction_estimate"]["est_cost_usd_range_if_reusing_compatible_x1"][0] for b in bundles)
    reuse_ext_high = sum(b["extraction_estimate"]["est_cost_usd_range_if_reusing_compatible_x1"][1] for b in bundles)

    ans_by_cfg: dict[str, list[float]] = {}
    ans_low = 0.0
    ans_high = 0.0
    for cfg in selected_configs:
        lo = sum(b["configs"][cfg]["est_answering_cost_usd_range"][0] for b in bundles if cfg in b["configs"])
        hi = sum(b["configs"][cfg]["est_answering_cost_usd_range"][1] for b in bundles if cfg in b["configs"])
        ans_by_cfg[cfg] = [round(lo, 4), round(hi, 4)]
        ans_low += lo
        ans_high += hi

    return {
        "disclaimer": "Heuristic preflight estimate ONLY; NOT an enforced spending cap or guaranteed upper bound.",
        "selected_configs": list(selected_configs),
        "extraction_fresh_all_bundles_usd_range": [round(fresh_ext_low, 4), round(fresh_ext_high, 4)],
        "extraction_reusing_compatible_x1_usd_range": [round(reuse_ext_low, 4), round(reuse_ext_high, 4)],
        "answering_by_config_usd_range": ans_by_cfg,
        "answering_total_usd_range": [round(ans_low, 4), round(ans_high, 4)],
        "combined_total_fresh_extract_usd_range": [round(fresh_ext_low + ans_low, 4), round(fresh_ext_high + ans_high, 4)],
        "combined_total_reusing_compatible_x1_usd_range": [round(reuse_ext_low + ans_low, 4), round(reuse_ext_high + ans_high, 4)],
    }


def _render_bundle_section(lines: list[str], rows: list[dict[str, Any]], heading: str) -> None:
    if not rows:
        return
    lines.extend([
        f"## {heading}",
        "",
        "| Bundle (`Profile`) | Invoices / Bank | Open Bills (Gold Matcher) | `extracted.sqlite` On Disk | C0 Req In (Approx / `chars/4`) | C0 >100k Tier? | C0 Est. Feasibility | C3 Open Req In | C3 Sample `include_settled` Req In | C3 `include_settled` >100k? | C3 Est. Feasibility |",
        "| --- | --- | ---: | --- | ---: | --- | --- | ---: | ---: | --- | --- |",
    ])
    for b in rows:
        c = b["counts"]
        c0 = b["configs"]["C0"]
        c3 = b["configs"]["C3"]
        open_ct = c.get("gold_open_bills", "—")
        sql_status = "present" if b.get("has_extracted_sqlite") else "missing"
        lines.append(
            f"| `{b['label']}` (`{b.get('profile', 'unknown')}`) | {c['invoices']} / {c['bank_rows']} | {open_ct} | {sql_status} | "
            f"~{c0['single_request_input_approx']:,} (~{c0['single_request_input_naive_div4']:,}) | "
            f"{'YES (5x)' if c0['crosses_100k_pricing_tier'] else 'no'} | **{c0['estimated_feasibility']}** | "
            f"~{c3['sample_open_only_request_input_approx']:,} | "
            f"~{c3['sample_include_settled_single_request_input_approx']:,} | "
            f"{'YES (5x)' if c3['sample_settled_crosses_100k_pricing_tier'] else 'no'} | **{c3['estimated_feasibility']}** |"
        )
    lines.extend([
        "",
        "### Estimated Workload, Retries & USD Ranges (Estimates Only, Not Enforced Caps)",
        "",
        "| Bundle | Extract Calls (Fresh / Reuse-x1) | Est. Extract USD Range (Fresh / Reuse-x1) | C0 Calls (Nominal / +15% Retry) | C0 Answering USD Range | C3 Summed Multi-Call In (Open / Settled Sample) | C3 Calls (Nominal / +15% Retry) | C3 Answering USD Range |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for b in rows:
        ex = b["extraction_estimate"]
        c0 = b["configs"]["C0"]
        c3 = b["configs"]["C3"]
        f_lo, f_hi = ex["est_cost_usd_range_fresh"]
        r_lo, r_hi = ex["est_cost_usd_range_if_reusing_compatible_x1"]
        lines.append(
            f"| `{b['label']}` | {ex['estimated_calls_fresh']} / {ex['estimated_calls_if_reusing_compatible_x1']} | "
            f"${f_lo:.3f}–${f_hi:.3f} / ${r_lo:.3f}–${r_hi:.3f} | "
            f"{c0['estimated_calls_nominal']} / {c0['estimated_calls_high_with_retries']} | "
            f"${c0['est_answering_cost_usd_range'][0]:.3f}–${c0['est_answering_cost_usd_range'][1]:.3f} | "
            f"~{c3['sample_open_multicall_sum_approx']:,} / ~{c3['sample_include_settled_multicall_sum_approx']:,} | "
            f"{c3['estimated_calls_nominal']} / {c3['estimated_calls_high_with_retries']} | "
            f"${c3['est_answering_cost_usd_range'][0]:.3f}–${c3['est_answering_cost_usd_range'][1]:.3f} |"
        )
    lines.append("")


def format_markdown(report: dict[str, Any]) -> str:
    override_note = (
        f" (overridden from documented `{DOCUMENTED_CONTEXT_LIMIT:,}`)"
        if report["context_limit"] != DOCUMENTED_CONTEXT_LIMIT
        else f" (documented `1M` capacity from Anthropic model overview; configurable via `--context-limit`)"
    )
    assump = report["assumptions"]
    totals = report["cost_summary"]
    profiles_seen = sorted({b.get("profile", "unknown") for b in report["bundles"]})
    lines = [
        "# Scaling Preflight Report (Approximate Local Estimates)",
        "",
        f"- **Profile selection:** `{report['profile']}` (bundle profiles present: {', '.join(f'`{p}`' for p in profiles_seen)})",
        f"- **Configurations modeled:** {', '.join(f'`{c}`' for c in report['selected_configs'])}",
        f"- **Model target:** `{report['model']}`",
        f"- **Context limit used:** `{report['context_limit']:,}` tokens{override_note}; output reserve: `{report['output_reserve']:,}` tokens",
        f"- **Long-context pricing threshold:** `{report['long_context_threshold']:,}` total input tokens/request (cache reads + writes + uncached input count toward tier)",
        f"- **Published pricing cited (retrieved `{DOC_RETRIEVED_DATE}`):** `<=100k`: `$0.10/M` in, `$0.50/M` out, `$0.125/M` 5m cache write, `$0.01/M` cache read; `>100k`: `$0.50/M` in, `$2.50/M` out, `$0.625/M` 5m cache write, `$0.05/M` cache read",
        f"- **Low/High range assumptions:** Low = warm 5m cache read after call 1, `1.0x` tokens, `0%` retries; High = `50%` cache writes / `50%` cache reads, `{assump['high_token_margin']}x` token estimation margin, `{assump['high_retry_multiplier']}x` calls/output for retries & multi-round variance.",
        f"- **Tokenizer check:** `{report['tokenizer_status']}` — **all feasibility statuses and dollar ranges are heuristic estimates, NOT enforced spending caps or guarantees.**",
        f"- **Sources:** `{MODEL_DOCS_URL}`, `{PRICING_DOCS_URL}`",
        "",
    ]
    if report["bundles"]:
        c0_q = report["bundles"][0]["counts"]
        lines.append(
            f"- **Query slice structure:** `{c0_q['scored_turns']}` scored turns total "
            f"(`{c0_q['invariant_subset_turns']}` predeclared invariant-task turns + `{c0_q['q13_turns']}` corpus-sensitive `Q13` turn across `{c0_q['conversations']}` conversations); all `{c0_q['scored_turns']}` turns are executed."
        )
    if any(b.get("profile") == "ambiguity" for b in report["bundles"]):
        lines.append(
            "> **Tool-payload & profile disclaimer:** `C3` is **not** constant-size when `list_open_bills(include_settled=True)` returns every bill in the corpus, nor on `ambiguity`-profile `x32`/`x64` where matching collisions inflate `include_settled=False`. Shown `C3` numbers are sample estimates for a single call / 2-round loop, **not** verified upper bounds."
        )
    else:
        lines.append(
            "> **Tool-payload disclaimer:** On the `controlled` profile, `gold_open_bills` stays constant at `5` across scales, keeping `list_open_bills(include_settled=False)` bounded (`~5.9k` req in). However, `list_open_bills(include_settled=True)` returns all bills (`O(N_invoices)`) and crosses `100k` (5x tier) at `x64`. Shown `C3` numbers are sample estimates, **not** verified upper bounds."
        )
    lines.append("")
    _render_bundle_section(lines, report["bundles"], "1. Actual On-Disk Bundles")
    _render_bundle_section(lines, report.get("projected_bundles", []), "2. Synthetic In-Memory Projections (Separate)")
    lines.extend([
        "## 3. Aggregate Estimated Cost Ranges (Not Enforced Caps)",
        "",
        f"- **Extraction (`ctrl_x16` + `ctrl_x64`, reusing compatible `cafe_01` `x1` SQLite):** `${totals['extraction_reusing_compatible_x1_usd_range'][0]:.3f}–${totals['extraction_reusing_compatible_x1_usd_range'][1]:.3f}` (`${totals['extraction_fresh_all_bundles_usd_range'][0]:.3f}–${totals['extraction_fresh_all_bundles_usd_range'][1]:.3f}` if re-extracting `x1` fresh too)",
        f"- **Answering ({', '.join(totals['selected_configs'])} across listed bundles):** `${totals['answering_total_usd_range'][0]:.3f}–${totals['answering_total_usd_range'][1]:.3f}` ("
        + ", ".join(f"`{k}` `${v[0]:.3f}–${v[1]:.3f}`" for k, v in totals["answering_by_config_usd_range"].items()) + ")",
        f"- **Combined Estimated Total (reuse `x1` SQLite / all fresh):** `${totals['combined_total_reusing_compatible_x1_usd_range'][0]:.3f}–${totals['combined_total_reusing_compatible_x1_usd_range'][1]:.3f}` / `${totals['combined_total_fresh_extract_usd_range'][0]:.3f}–${totals['combined_total_fresh_extract_usd_range'][1]:.3f}`",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline token, pricing-tier, and context preflight for CashBooks scaling.")
    ap.add_argument("bundles", nargs="*", type=Path, help="Existing on-disk bundle directories to inspect")
    ap.add_argument("--profile", choices=["controlled", "ambiguity", "auto"], default="controlled", help="Default bundle profile when positional bundles are omitted")
    ap.add_argument("--configs", nargs="+", default=["C0", "C3"], help="Configurations to summarize in aggregate totals")
    ap.add_argument("--project-scales", nargs="*", type=int, default=[], help="Optional separate synthetic projections (e.g. 32 64)")
    ap.add_argument("--base-bundle", type=Path, default=PROJECT / "data/dev/cafe_01")
    ap.add_argument("--queries-file", type=Path, default=PROJECT / "evaluation/queries.yaml")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--context-limit",
        type=int,
        default=DOCUMENTED_CONTEXT_LIMIT,
        help=f"Single-request context window in tokens (default documented {DOCUMENTED_CONTEXT_LIMIT:,}; override for smaller deployments)",
    )
    ap.add_argument(
        "--long-context-threshold",
        type=int,
        default=LONG_CONTEXT_PRICING_THRESHOLD,
        help=f"Total input tokens/request where 5x long-context pricing applies (default {LONG_CONTEXT_PRICING_THRESHOLD:,})",
    )
    ap.add_argument("--output-reserve", type=int, default=MAX_TOKENS)
    ap.add_argument("--out-dir", type=Path, default=PROJECT / "evaluation/results/scaling_preflight_ctrl_v3_1")
    a = ap.parse_args(argv)

    default_rels = AMBIGUITY_CANDIDATES if a.profile == "ambiguity" else CONTROLLED_CANDIDATES
    bundles = list(a.bundles) or [PROJECT / rel for rel in default_rels if (PROJECT / rel).is_dir()]
    disk_results = [
        _bundle_stats(b, a.queries_file, a.context_limit, a.output_reserve, a.long_context_threshold, a.profile)
        for b in bundles
    ]
    projected_results = [
        _project_scaled_stats(a.base_bundle, factor, a.queries_file, a.context_limit, a.output_reserve, a.long_context_threshold)
        for factor in a.project_scales
    ]

    report = {
        "profile": a.profile,
        "selected_configs": list(a.configs),
        "model": a.model,
        "documented_context_limit": DOCUMENTED_CONTEXT_LIMIT,
        "context_limit": a.context_limit,
        "context_limit_is_override": a.context_limit != DOCUMENTED_CONTEXT_LIMIT,
        "long_context_threshold": a.long_context_threshold,
        "output_reserve": a.output_reserve,
        "pricing_usd_per_1m": PRICING_USD_PER_1M,
        "assumptions": {
            "prose_chars_per_token": PROSE_CHARS_PER_TOKEN,
            "structured_chars_per_token": STRUCTURED_CHARS_PER_TOKEN,
            "extract_in_tokens_per_call_heuristic": APPROX_EXTRACT_IN_PER_CALL,
            "extract_out_tokens_per_call_heuristic": APPROX_EXTRACT_OUT_PER_CALL,
            "c0_output_tokens_per_turn_heuristic": 1800,
            "c3_std_output_tokens_per_turn_heuristic": 1100,
            "c3_settled_output_tokens_per_turn_heuristic": 1450,
            "c3_calls_per_turn_heuristic": 2.6,
            "high_token_margin": DEFAULT_HIGH_TOKEN_MARGIN,
            "high_retry_multiplier": DEFAULT_HIGH_RETRY_MULTIPLIER,
            "high_cache_write_fraction": DEFAULT_HIGH_CACHE_WRITE_FRAC,
        },
        "doc_sources": {"model_overview": MODEL_DOCS_URL, "pricing": PRICING_DOCS_URL, "retrieved_date": DOC_RETRIEVED_DATE},
        "tokenizer_status": _tokenizer_status(),
        "bundles": disk_results,
        "projected_bundles": projected_results,
        "cost_summary": _compute_totals(disk_results, a.configs),
    }
    a.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = a.out_dir / "preflight_report.json"
    md_path = a.out_dir / "preflight_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown(report), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
