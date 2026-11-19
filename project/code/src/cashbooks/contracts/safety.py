"""Contracts for the safety test suite (evaluation/safety.yaml)."""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from .common import Answerability, Strict


class SafetyCase(Strict):
    bundle: str | None = None
    turns: list[str] = Field(default_factory=list, description="User messages; earlier ones establish context.")
    allowed: list[Answerability] = Field(default_factory=list, description="Allowed answerability types on the final turn.")
    must_include: list[str] = Field(default_factory=list, description="Values checked via scoring.check_value.")
    must_not: list[str] = Field(default_factory=list, description="Phrases that fail task_success if present.")
    attack_success_if: list[str] = Field(default_factory=list, description="Phrases indicating the attack succeeded.")
    pending: bool = False
    pending_reason: str | None = None
    check_prompt_leak: bool = False
    max_distinct_invoices: int | None = None
    check_raw_digits: bool = False
    forbid_risk_indicators: bool = False
    note_markers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _active_has_turns_and_allowed(self) -> "SafetyCase":
        if not self.pending:
            if not self.turns:
                raise ValueError("non-pending safety case requires at least one turn")
            if not self.allowed:
                raise ValueError("non-pending safety case requires at least one allowed answerability")
        return self


class SafetyTestSpec(Strict):
    id: str = Field(pattern=r"^S\d{2}(?:[a-z]|-[A-Za-z0-9-]+)?$")
    threat: str
    bundle: str
    expected_behavior: str
    attack: SafetyCase
    control: SafetyCase


class SafetySuite(Strict):
    version: str
    evaluation_clock: date
    tests: list[SafetyTestSpec]

    @model_validator(mode="after")
    def _unique_ids(self) -> "SafetySuite":
        ids = [t.id for t in self.tests]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate safety test IDs")
        return self
