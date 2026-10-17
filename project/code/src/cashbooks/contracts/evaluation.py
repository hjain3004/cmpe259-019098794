"""Contracts for the frozen query file (eval/queries.yaml) and the per-run log row."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field, model_validator

from .common import Answerability, EvidenceId, Strict

ReasoningLabel = Literal[
    "lookup", "aggregation", "temporal", "linking", "comparison", "dialogue", "abstention"
]
Category = Literal["common", "external_data", "multi_turn", "edge_case"]
Configuration = Literal["C1", "C2", "C3", "C4"]


class TurnSpec(Strict):
    text: str
    scored: bool = Field(True, description="False for setup turns that only establish context.")
    expected: Answerability
    expected_behavior: str = Field(description="What a correct response does, in one sentence.")
    gold_values: dict[str, Any] = Field(
        default_factory=dict,
        description="Exact values to check, e.g. {'balance': '1240.00 USD', 'status': 'partial'}. "
        "Filled from the scenario ledger once bundles exist.",
    )
    gold_evidence: list[EvidenceId] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list, description="Phrases or acts that fail the turn.")


class ConversationSpec(Strict):
    id: str = Field(pattern=r"^Q\d{2}$")
    category: Category
    scenario: str = Field(description="Scenario family the bundle must contain.")
    labels: list[ReasoningLabel] = Field(min_length=1)
    stretch: bool = False
    turns: list[TurnSpec] = Field(min_length=1)
    notes: str | None = None

    @model_validator(mode="after")
    def _has_scored_turn(self) -> "ConversationSpec":
        if not any(t.scored for t in self.turns):
            raise ValueError("a conversation needs at least one scored turn")
        return self


class QuerySuite(Strict):
    version: str
    evaluation_clock: date
    status: Literal["draft", "frozen"]
    conversations: list[ConversationSpec]

    @model_validator(mode="after")
    def _unique_ids(self) -> "QuerySuite":
        ids = [c.id for c in self.conversations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate conversation IDs")
        return self


class LogRow(Strict):
    """One row per (configuration, conversation, turn). Every reported number comes from these."""

    query_id: str
    turn_index: int
    turn_text: str
    scenario: str
    business_type: str
    split: Literal["dev", "test_seen", "test_heldout"]
    configuration: Configuration
    model_version: str
    prompt_version: str
    code_commit: str
    context: list[dict[str, Any]] = Field(description="Retrieved chunks (C1/C2) or tool calls with args and outputs (C3/C4).")
    raw_response: str
    parsed_ok: bool
    expected: Answerability
    success: bool | None = None  # None until scored
    scores: dict[str, Any] = Field(default_factory=dict)
    error_label: Literal[
        "extraction", "entity_linking", "payment_linking", "retrieval", "tool_selection",
        "reasoning", "grounding", "dialogue", "abstention", "safety",
    ] | None = None
    notes: str = ""
    latency_ms: int
    input_tokens: int
    output_tokens: int

    def course_projection(self) -> dict[str, Any]:
        """The five fields the course requires."""
        return {
            "query": self.turn_text,
            "expected_behavior": self.expected.value,
            "response": self.raw_response,
            "success": self.success,
            "notes": self.notes,
        }
