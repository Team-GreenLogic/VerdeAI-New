"""Document schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: str
    websocket_url: str


class DocumentItem(BaseModel):
    document_id: str
    filename: str
    status: str
    pages: int | None
    uploaded_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentItem]


class DocumentDeleteResponse(BaseModel):
    status: str


class WSTicketResponse(BaseModel):
    ticket: str
    expires_in: int
