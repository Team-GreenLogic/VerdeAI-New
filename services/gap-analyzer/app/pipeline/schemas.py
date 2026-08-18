"""Pydantic schemas for validated, structured LLM output in the gap-analysis pipeline.

Every LLM call in the clause pipeline now returns JSON that is parsed AND validated
against one of these models (see ``verdeai_shared.llm.structured.stream_structured``)
instead of a bare ``json.loads``. This is the "schema-validated object" half of the
Docling-Graph-inspired accuracy design; the other half — deterministic provenance
grounding — lives in ``app.pipeline.validation``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Decision = Literal["Met", "Partially Met", "Not Met", "Insufficient Evidence"]
FindingStatus = Literal["satisfied", "partial", "unmet"]


class Citation(BaseModel):
    """A single evidence citation produced by the LLM.

    ``chunk_id`` is a free-form string (the LLM writes things like "Chunk 3");
    grounding validation resolves it against the retrieved chunk list.
    """

    type: Literal["chunk", "org_profile"]
    chunk_id: str | None = None
    field_path: str | None = None
    page: int | str | None = None


class StateDiffEntry(BaseModel):
    expected: str | float | bool | None = None
    actual: str | float | bool | None = None
    satisfied: bool = False
    kind: str | None = None


class StateDiff(BaseModel):
    """Output schema for the state_compare node."""

    state_diff: dict[str, StateDiffEntry] = Field(default_factory=dict)
    reference_context: dict[str, str | float | bool | None] = Field(default_factory=dict)


class SubRequirementFinding(BaseModel):
    """Per-sub-requirement verdict, the deterministic basis for the clause decision."""

    req_id: str
    status: FindingStatus
    citation_ids: list[int] = Field(default_factory=list)
    notes: str = ""


class GapVerdict(BaseModel):
    """Output schema for the gap_analyse node."""

    decision: Decision
    confidence: float
    reasoning: str
    findings: list[SubRequirementFinding] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    # Not produced by the LLM — stamped at persist time with the document ids whose
    # chunks were retrieved for this clause, so delta re-analysis can tell which
    # verdicts a superseded/removed document invalidates.
    source_document_ids: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class EvidenceGrade(BaseModel):
    """Output schema for the (optional) LLM evidence-relevance grader."""

    relevant_indices: list[int] = Field(default_factory=list)


class GroundednessResult(BaseModel):
    """Output schema for the LLM groundedness judge in verify_grounding."""

    grounded: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    reason: str = ""
