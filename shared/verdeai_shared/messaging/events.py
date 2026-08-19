"""Versioned Pydantic event payloads for inter-service messaging."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _new_event_id() -> str:
    return str(uuid.uuid4())


class DocumentUploaded(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    profile_id: str
    document_id: str
    filename: str
    sha256: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentReady(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    document_id: str
    chunks_indexed: int


class DocumentDeleted(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    profile_id: str
    document_id: str


class AnalysisRequested(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    profile_id: str
    analysis_id: str
    scope: Literal["full"] | dict[str, list[str]]
    version_id: str = "iso-14001-2015"
    # Delta re-analysis: when mode == "delta", the worker copies the parent
    # analysis's verdicts forward and only re-runs clauses affected by evidence
    # added or removed since ``baseline_at`` (the parent analysis's created_at).
    mode: Literal["full", "delta"] = "full"
    parent_analysis_id: str | None = None
    baseline_at: datetime | None = None


class AnalysisGapsReady(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    analysis_id: str
    gap_count: int


class AnalysisMissingReady(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    analysis_id: str


class AnalysisRecommendationsReady(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    analysis_id: str


class AnalysisCompleted(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    analysis_id: str


class IsoVersionBuildRequested(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    version_id: str
    build_job_id: str
    tenant_id: str = ""
    source_docs: list[dict[str, str]]  # [{gridfs_id, filename}]
    requested_by: str  # admin email
