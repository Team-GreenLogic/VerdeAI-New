"""Chat RAG SSE endpoint."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.chat_history import ChatHistoryRepository
from verdeai_shared.db.repositories.org_profiles import OrgProfilesRepository

from app.config import settings
from app.pipeline.history import append_turn, load_history
from app.pipeline.rag import rag_stream

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    profile_id: str
    session_id: str | None = None


class ChatSessionCreate(BaseModel):
    profile_id: str


class ChatSessionResponse(BaseModel):
    session_id: str


class ChatSessionSummary(BaseModel):
    session_id: str
    profile_id: str | None = None
    title: str
    last_message_at: str
    message_count: int


class ChatMessageOut(BaseModel):
    role: str
    content: str
    citations: list[dict] = []
    created_at: str


async def _get_owned_profile(db, tenant_id: str, profile_id: str) -> dict:
    profile = await OrgProfilesRepository(db, tenant_id).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Org profile not found")
    return profile


@router.post("/session", response_model=ChatSessionResponse)
async def create_session(body: ChatSessionCreate, principal: CurrentPrincipal) -> ChatSessionResponse:
    """Create a new chat session. Returns a session_id to use in subsequent requests."""
    db = get_database()
    await _get_owned_profile(db, principal.tenant_id, body.profile_id)
    return ChatSessionResponse(session_id=str(uuid.uuid4()))


@router.get("/sessions", response_model=list[ChatSessionSummary])
async def list_sessions(
    principal: CurrentPrincipal,
    profile_id: str | None = Query(default=None),
) -> list[ChatSessionSummary]:
    """List this tenant's past chat sessions, most recently active first."""
    db = get_database()
    if profile_id:
        await _get_owned_profile(db, principal.tenant_id, profile_id)
    rows = await ChatHistoryRepository(db, principal.tenant_id).list_sessions(profile_id=profile_id)
    return [
        ChatSessionSummary(
            session_id=r["session_id"],
            profile_id=r.get("profile_id"),
            title=(r.get("title") or "")[:80],
            last_message_at=r["last_message_at"].isoformat(),
            message_count=r["message_count"],
        )
        for r in rows
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def get_session_messages(session_id: str, principal: CurrentPrincipal) -> list[ChatMessageOut]:
    """Full message history for one session, for resuming a past conversation."""
    db = get_database()
    rows = await ChatHistoryRepository(db, principal.tenant_id).list_all(session_id)
    return [
        ChatMessageOut(
            role=r["role"],
            content=r["content"],
            citations=r.get("citations", []),
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, principal: CurrentPrincipal) -> dict[str, int]:
    """Delete a past conversation."""
    db = get_database()
    deleted = await ChatHistoryRepository(db, principal.tenant_id).delete_session(session_id)
    return {"deleted": deleted}


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
    profile_id = body.profile_id
    session_id = body.session_id or str(uuid.uuid4())
    question = body.question.strip()

    if not question:
        async def _empty():
            yield {"data": json.dumps({"type": "error", "content": "Empty question"})}
            yield {"data": json.dumps({"type": "done"})}
        return EventSourceResponse(_empty())

    db = get_database()
    await _get_owned_profile(db, tenant_id, profile_id)

    logger.info("Chat request", tenant_id=tenant_id, profile_id=profile_id, session_id=session_id)

    async def _generate():
        answer_parts: list[str] = []
        citations: list[dict] = []
        done_yielded = False
        try:
            # Load history inside the generator so Redis errors surface as SSE errors
            history = await load_history(tenant_id, session_id, settings.CHAT_HISTORY_WINDOW)

            async for event in rag_stream(db, tenant_id, profile_id, question, history):
                if event["type"] == "token":
                    answer_parts.append(event["content"])
                if event["type"] == "citations":
                    citations = event.get("citations", [])
                if event["type"] == "done":
                    done_yielded = True
                yield {"data": json.dumps(event)}
        except Exception as exc:
            logger.error("Chat stream error", error=str(exc))
            yield {"data": json.dumps({"type": "error", "content": "An internal error occurred"})}
        finally:
            if not done_yielded:
                yield {"data": json.dumps({"type": "done"})}

        # Persist turn: Redis (short-lived prompt-context window) + Mongo (durable, user-facing history)
        full_answer = "".join(answer_parts)
        if full_answer:
            try:
                await append_turn(
                    tenant_id, session_id, question, full_answer,
                    settings.CHAT_HISTORY_WINDOW,
                )
            except Exception as exc:
                logger.warning("Failed to save chat history", error=str(exc))

            try:
                history_repo = ChatHistoryRepository(db, tenant_id)
                await history_repo.append(session_id, "user", question, profile_id=profile_id)
                await history_repo.append(
                    session_id, "assistant", full_answer, citations, profile_id=profile_id
                )
            except Exception as exc:
                logger.warning("Failed to persist chat history to Mongo", error=str(exc))

    return EventSourceResponse(_generate())
