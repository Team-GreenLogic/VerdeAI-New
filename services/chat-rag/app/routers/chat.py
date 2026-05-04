"""Chat RAG SSE endpoint."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.db.mongo import get_database

from app.config import settings
from app.pipeline.history import append_turn, load_history
from app.pipeline.rag import rag_stream

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None


class ChatSessionResponse(BaseModel):
    session_id: str


@router.post("/session", response_model=ChatSessionResponse)
async def create_session(principal: CurrentPrincipal) -> ChatSessionResponse:
    """Create a new chat session. Returns a session_id to use in subsequent requests."""
    return ChatSessionResponse(session_id=str(uuid.uuid4()))


@router.post("")
async def chat(
    body: ChatRequest,
    principal: CurrentPrincipal,
) -> EventSourceResponse:
    """Stream a RAG-grounded answer via Server-Sent Events.

    SSE event format:
        data: {"type": "token", "content": "<text>"}
        data: {"type": "citations", "citations": [...]}
        data: {"type": "done"}
        data: {"type": "error", "content": "<message>"}  (on failure)
    """
    tenant_id = principal.tenant_id
    session_id = body.session_id or str(uuid.uuid4())
    question = body.question.strip()

    if not question:
        async def _empty():
            yield {"data": json.dumps({"type": "error", "content": "Empty question"})}
            yield {"data": json.dumps({"type": "done"})}
        return EventSourceResponse(_empty())

    db = get_database()

    # Load conversation history
    history = await load_history(tenant_id, session_id, settings.CHAT_HISTORY_WINDOW)

    logger.info("Chat request", tenant_id=tenant_id, session_id=session_id)

    async def _generate():
        answer_parts: list[str] = []

        async for event in rag_stream(db, tenant_id, question, history):
            if event["type"] == "token":
                answer_parts.append(event["content"])
            yield {"data": json.dumps(event)}

        # Persist turn to history after streaming completes
        full_answer = "".join(answer_parts)
        if full_answer:
            try:
                await append_turn(
                    tenant_id, session_id, question, full_answer,
                    settings.CHAT_HISTORY_WINDOW,
                )
            except Exception as exc:
                logger.warning("Failed to save chat history", error=str(exc))

    return EventSourceResponse(_generate())
