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
    document_id: str


class AnalysisRequested(BaseModel):
    schema_version: int = 1
    event_id: str = Field(default_factory=_new_event_id)
    tenant_id: str
    analysis_id: str
    scope: Literal["full"] | dict[str, list[str]]


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
