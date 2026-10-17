"""The response contract: every configuration (C1-C4) returns this object,
so one scorer handles all four and the interface renders citations the same way.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from .common import Answerability, EvidenceId, Money, Strict


class Citation(Strict):
    evidence_id: EvidenceId
    supports: str = Field(description="The specific claim in the answer this record supports.")


class Calculation(Strict):
    """Shown so the owner can check the arithmetic, e.g. total - payments - credits."""

    steps: list[str] = Field(min_length=1)
    result: Money


class AssistantResponse(Strict):
    answerability: Answerability
    answer: str = Field(min_length=1, max_length=1500)
    as_of: date
    evidence: list[Citation] = Field(default_factory=list)
    calculation: Calculation | None = None
    risk_indicators: list[str] = Field(
        default_factory=list,
        description="Observable discrepancies only (e.g. payment details differ from the record on file).",
    )
    clarifying_question: str | None = None
    next_step: str | None = None

    @model_validator(mode="after")
    def _shape_matches_answerability(self) -> "AssistantResponse":
        a = self.answerability
        if a is Answerability.CLARIFY:
            q = self.clarifying_question
            if not q or q.count("?") != 1:
                raise ValueError("CLARIFY needs exactly one clarifying question")
        elif self.clarifying_question is not None:
            raise ValueError("only CLARIFY may carry a clarifying_question")
        if a in (Answerability.ANSWER, Answerability.WARN) and not self.evidence:
            raise ValueError(f"{a.value} needs at least one citation")
        if a is Answerability.WARN and not self.risk_indicators:
            raise ValueError("WARN needs at least one risk indicator")
        if a is Answerability.ABSTAIN and self.calculation is not None:
            raise ValueError("ABSTAIN must not present a calculated result")
        return self
