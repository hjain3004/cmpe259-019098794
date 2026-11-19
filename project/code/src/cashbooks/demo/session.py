"""Plain-Python chat session over one scenario bundle (no UI imports)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from cashbooks.configs.answer import RetrievalConfig, ToolConfig, Turn, build_configs, format_turn_assistant
from cashbooks.configs.dialogue_state import DialogueState, derive_dialogue_state
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.evaluation import ConversationSpec, QuerySuite
from cashbooks.contracts.postprocess import mask_numbers, postprocess
from cashbooks.contracts.records import VendorFingerprint
from cashbooks.contracts.response import AssistantResponse
from cashbooks.llm.base import LLM
from cashbooks.store.db import SCHEMA, Store
from cashbooks.store.load_gold import load_gold


@dataclass
class ResolvedCitation:
    evidence_id: str
    supports: str
    quote: str


@dataclass
class ToolTrace:
    name: str
    args: dict
    result_preview: str


@dataclass
class ChatTurnResult:
    config_name: str
    response: AssistantResponse | None
    parse_error: str | None = None
    answerability: Answerability | None = None
    answer: str = ""
    calculation_steps: list[str] = field(default_factory=list)
    calculation_result: str | None = None
    risk_indicators: list[str] = field(default_factory=list)
    clarifying_question: str | None = None
    next_step: str | None = None
    citations: list[ResolvedCitation] = field(default_factory=list)
    tool_calls: list[ToolTrace] = field(default_factory=list)
    retrieved_chunks: list[dict] = field(default_factory=list)
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    issues: list[str] = field(default_factory=list)


def _thread_safe_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _resolve_store_quote(store: Store | None, evidence_id: str) -> str | None:
    if store is None:
        return None
    if evidence_id.startswith("span_"):
        sp = store.span(evidence_id)
        if sp is not None:
            return mask_numbers(sp.quote)
    elif evidence_id.startswith("txn_"):
        tx = store.txn(evidence_id)
        if tx is not None:
            return mask_numbers(f"{tx.posted_on.isoformat()} | {tx.descriptor} | {tx.amount:.2f} {tx.currency}")
    elif evidence_id.startswith("vh_"):
        fps = store._all(VendorFingerprint, "evidence_id = ?", (evidence_id,))
        if fps:
            fp = fps[0]
            vname = store.vendor_name(fp.vendor_id)
            parts = [vname]
            if fp.bank_name:
                parts.append(fp.bank_name)
            parts.append(f"account ****{fp.account_last4}")
            if fp.routing_last4:
                parts.append(f"routing ****{fp.routing_last4}")
            parts.append(f"verified {fp.verified_on.isoformat()}")
            if fp.trusted_contact:
                parts.append(f"contact {fp.trusted_contact}")
            return mask_numbers(", ".join(parts))
    return None


def resolve_turn_texts(conv: ConversationSpec, gold_entry: list | dict | None) -> list[str]:
    """Return the per-turn texts for a conversation, applying any bundle-level text overrides."""
    if gold_entry is None:
        return [t.text for t in conv.turns]
    if isinstance(gold_entry, dict):
        gold_turns = list(gold_entry.get("turns", []))
        setup_text = gold_entry.get("setup_text")
    else:
        gold_turns = list(gold_entry)
        setup_text = None
    out: list[str] = []
    gi = 0
    for turn in conv.turns:
        if turn.scored:
            g = gold_turns[gi] if gi < len(gold_turns) else {}
            gi += 1
            out.append(str(g.get("text") or turn.text))
        else:
            out.append(str(setup_text or turn.text))
    return out


class ChatSession:
    """Stateful multi-turn chat session over a CashBooks bundle."""

    def __init__(self, bundle: str | Path, config_name: str, llm: LLM):
        self.bundle = Path(bundle)
        self.llm = llm
        ledger = json.loads((self.bundle / "ledger.json").read_text())
        biz = ledger["business"]
        self.business_name: str = biz["name"]
        self.business_id: str = biz["business_id"]
        self.as_of: date = date.fromisoformat(biz["evaluation_clock"])

        self.gold_store, _ = load_gold(self.bundle, _thread_safe_memory_db())
        self.extracted_store: Store | None = None
        xdb = self.bundle / "extracted.sqlite"
        if xdb.exists():
            conn = sqlite3.connect(str(xdb), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self.extracted_store = Store(conn, self.business_id)

        self.history: list[Turn] = []
        self._configs: dict = {}
        self.config_name: str = config_name
        self.config = self._get_or_build(config_name)

    def _get_or_build(self, name: str):
        if name not in self._configs:
            built = build_configs(
                self.bundle,
                self.gold_store,
                self.extracted_store,
                self.business_name,
                self.as_of,
                [name],
            )
            self._configs[name] = built[name]
        return self._configs[name]

    @property
    def dialogue_state(self) -> DialogueState:
        """Structured conversation state derived strictly from displayed turns."""
        return derive_dialogue_state(self.history)

    def reset(self) -> None:
        """Clear conversation history."""
        self.history.clear()

    def switch_config(self, name: str) -> None:
        """Switch active configuration and reset conversation history."""
        self.config = self._get_or_build(name)
        self.config_name = name
        self.reset()

    def turn_texts(self, query_id: str, queries_path: Path | None = None) -> list[str]:
        """Return the turn texts for `query_id`, applying any `text` overrides in the bundle's gold.yaml."""
        qpath = queries_path or (self.bundle.parents[2] / "evaluation" / "queries.yaml")
        suite = QuerySuite.model_validate(yaml.safe_load(qpath.read_text(encoding="utf-8")))
        conv = next(c for c in suite.conversations if c.id == query_id)
        gold_path = self.bundle / "gold.yaml"
        gold = yaml.safe_load(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else {}
        return resolve_turn_texts(conv, gold.get(query_id))

    def _resolve_quote(self, evidence_id: str) -> str:
        cfg = self.config
        if isinstance(cfg, RetrievalConfig):
            for chunk in cfg.retriever.chunks:
                if chunk.chunk_id == evidence_id:
                    return mask_numbers(chunk.text)
            q = _resolve_store_quote(self.extracted_store, evidence_id)
            if q is not None:
                return q
            q = _resolve_store_quote(self.gold_store, evidence_id)
            if q is not None:
                return q
        elif isinstance(cfg, ToolConfig):
            q = _resolve_store_quote(cfg.store, evidence_id)
            if q is not None:
                return q
        return "(quote unavailable)"

    def ask(self, question: str) -> ChatTurnResult:
        """Run one user turn against the active configuration and update history."""
        o = self.config.answer(self.llm, self.history, question)
        raw = o.result.text
        pp = postprocess(raw, o.known_evidence, default_as_of=self.as_of) if raw else None
        resp = pp.response if pp else None

        issues: list[str] = []
        if o.result.error:
            issues.append(f"llm_error: {o.result.error[:300]}")
        if pp:
            issues += pp.issues + [f"wording: {w}" for w in pp.wording_flags]

        tool_calls: list[ToolTrace] = []
        retrieved_chunks: list[dict] = []
        if isinstance(self.config, ToolConfig):
            for tc in o.result.tool_calls:
                preview = mask_numbers(tc.result)
                if len(preview) > 400:
                    preview = preview[:400] + "..."
                tool_calls.append(ToolTrace(name=tc.name, args=tc.args, result_preview=preview))
        else:
            retrieved_chunks = list(o.context)

        self.history.append(Turn(question, format_turn_assistant(resp, raw)))

        if resp is None:
            err = "; ".join(issues) if issues else "empty response"
            return ChatTurnResult(
                config_name=self.config_name,
                response=None,
                parse_error=mask_numbers(err),
                tool_calls=tool_calls,
                retrieved_chunks=retrieved_chunks,
                latency_ms=o.result.latency_ms,
                input_tokens=o.result.input_tokens,
                output_tokens=o.result.output_tokens,
                issues=[mask_numbers(x) for x in issues],
            )

        citations = [
            ResolvedCitation(
                evidence_id=c.evidence_id,
                supports=mask_numbers(c.supports),
                quote=self._resolve_quote(c.evidence_id),
            )
            for c in resp.evidence
        ]
        calc_steps = [mask_numbers(s) for s in resp.calculation.steps] if resp.calculation else []
        calc_res = (
            f"{resp.calculation.result.amount:.2f} {resp.calculation.result.currency}"
            if resp.calculation
            else None
        )

        return ChatTurnResult(
            config_name=self.config_name,
            response=resp,
            answerability=resp.answerability,
            answer=resp.answer,
            calculation_steps=calc_steps,
            calculation_result=calc_res,
            risk_indicators=[mask_numbers(r) for r in resp.risk_indicators],
            clarifying_question=resp.clarifying_question,
            next_step=resp.next_step,
            citations=citations,
            tool_calls=tool_calls,
            retrieved_chunks=retrieved_chunks,
            latency_ms=o.result.latency_ms,
            input_tokens=o.result.input_tokens,
            output_tokens=o.result.output_tokens,
            issues=[mask_numbers(x) for x in issues],
        )
