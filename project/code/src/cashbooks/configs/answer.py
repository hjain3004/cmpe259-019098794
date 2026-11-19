"""The configurations. Each turns (conversation so far, new question) into a
response; only the context block and the tool list differ between them.

    C0  whole raw corpus in context (no retrieval)
    C1  BM25 over raw document chunks
    C2  BM25 over serialized extracted records (same retriever and k)
    C3  seven read-only tools over the extracted records
    C4  the same tools over hand-verified gold records
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from cashbooks.configs.retrieval import BM25Retriever, build_raw_chunks, build_record_chunks, render_context
from cashbooks.contracts.postprocess import mask_numbers
from cashbooks.contracts.response import AssistantResponse
from cashbooks.contracts.tools import tool_definitions
from cashbooks.llm.base import LLM, LLMResult, Message, simplify_schema
from cashbooks.store.db import Store
from cashbooks.tools.registry import run_tool

PROMPTS = Path(__file__).resolve().parents[4] / "prompts"
PROMPT_VERSION = "answer_system_v2"
K = 8          # chosen on the café development scenario (recall@8), then frozen
MAX_TOOL_CALLS = 6

TOOL_GUIDE = (
    "\n\n## Tools\n\nLook facts up with the tools before answering; never guess an amount or a status. "
    "Tool results list evidence IDs; cite those. Use get_source_evidence to read the exact wording behind an ID. "
    "list_open_bills hides paid bills unless include_settled is true. match_payments can look up bank debits by amount and/or date."
)


def system_prompt(business_name: str, as_of: date, tools: bool, version: str = PROMPT_VERSION) -> str:
    text = (PROMPTS / f"{version}.md").read_text()
    kind = "tool results" if tools else "retrieved context"
    out = text.format(business_name=business_name, as_of=as_of.isoformat(), evidence_kind=kind)
    return out + (TOOL_GUIDE if tools else "")


def format_turn_assistant(resp: AssistantResponse | None, raw: str = "") -> str:
    """Format the full displayed reply for conversation history across all configurations."""
    if resp is None:
        return mask_numbers(raw)[:800]
    parts = [resp.answer]
    if resp.clarifying_question:
        parts.append(f"Clarifying question: {resp.clarifying_question}")
    if resp.calculation:
        steps = "; ".join(resp.calculation.steps)
        res = resp.calculation.result
        parts.append(f"Calculation: {steps} = {res.amount:.2f} {res.currency}")
    if resp.risk_indicators:
        parts.append("Risk indicators: " + "; ".join(resp.risk_indicators))
    if resp.next_step:
        parts.append(f"Next step: {resp.next_step}")
    return "\n".join(parts)


@dataclass
class Turn:
    user: str
    assistant: str  # the previous reply's answer text, shown back to the model


@dataclass
class ConfigOutput:
    result: LLMResult
    context: list[dict] = field(default_factory=list)  # retrieved chunks or tool calls, for the log
    known_evidence: set[str] = field(default_factory=set)


def _history(history: list[Turn], question: str, context: str | None) -> list[Message]:
    msgs: list[Message] = []
    for t in history:
        msgs.append(Message("user", t.user))
        msgs.append(Message("model", t.assistant))
    prompt = question if context is None else f"RETRIEVED CONTEXT\n\n{context}\n\nQUESTION\n{question}"
    msgs.append(Message("user", prompt))
    return msgs


class RetrievalConfig:
    """C0 (all raw chunks, no retrieval), C1 and C2 (top-k BM25)."""

    def __init__(self, name: str, retriever: BM25Retriever, business_name: str, as_of: date, k: int | None = K):
        self.name, self.retriever, self.k = name, retriever, k
        self.system = system_prompt(business_name, as_of, tools=False)
        self.known = {c.chunk_id for c in retriever.chunks}

    def answer(self, llm: LLM, history: list[Turn], question: str) -> ConfigOutput:
        if self.k is None:
            chunks = list(self.retriever.chunks)
        else:
            chunks = self.retriever.search_conversation([t.user for t in history] + [question], k=self.k)
        res = llm.complete(self.system, _history(history, question, render_context(chunks)))
        ctx = [{"chunk_id": c.chunk_id, "source": c.source} for c in chunks]
        return ConfigOutput(res, ctx, self.known)


class ToolConfig:
    """C3 and C4."""

    def __init__(self, name: str, store: Store, business_name: str, as_of: date):
        self.name, self.store = name, store
        self.system = system_prompt(business_name, as_of, tools=True)
        self.tools = [{**t, "input_schema": simplify_schema(t["input_schema"])} for t in tool_definitions()]
        self.known = store.evidence_ids()

    def answer(self, llm: LLM, history: list[Turn], question: str) -> ConfigOutput:
        res = llm.complete_with_tools(self.system, _history(history, question, None), self.tools,
                                      lambda name, args: run_tool(self.store, name, args), MAX_TOOL_CALLS)
        ctx = [{"tool": c.name, "args": c.args, "result": c.result[:2000]} for c in res.tool_calls]
        return ConfigOutput(res, ctx, self.known)


def build_configs(bundle: Path, gold_store: Store, extracted_store: Store | None, business_name: str,
                  as_of: date, names: list[str]) -> dict:
    out = {}
    for n in names:
        if n == "C0":
            out[n] = RetrievalConfig("C0", BM25Retriever(build_raw_chunks(bundle)), business_name, as_of, k=None)
        elif n == "C1":
            out[n] = RetrievalConfig("C1", BM25Retriever(build_raw_chunks(bundle)), business_name, as_of)
        elif n == "C2":
            if extracted_store is None:
                raise SystemExit("C2 needs extracted records: run evaluation/extract_bundle.py first")
            out[n] = RetrievalConfig("C2", BM25Retriever(build_record_chunks(extracted_store, as_of)), business_name, as_of)
        elif n == "C3":
            if extracted_store is None:
                raise SystemExit("C3 needs extracted records: run evaluation/extract_bundle.py first")
            out[n] = ToolConfig("C3", extracted_store, business_name, as_of)
        elif n == "C4":
            out[n] = ToolConfig("C4", gold_store, business_name, as_of)
        else:
            raise SystemExit(f"unknown configuration {n}")
    return out
