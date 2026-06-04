"""Chat RAG pipeline — retrieval, context assembly, and LLM streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import verdeai_shared as _vs_pkg
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from verdeai_shared.llm.openrouter_client import stream
from verdeai_shared.retrieval.embedder import embed_query
from verdeai_shared.retrieval.hybrid import hybrid_retrieve
from verdeai_shared.settings import settings

_PROMPTS_DIR = Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

# Org profile top-level field paths
_ORG_FIELDS = {
    "org_name": "org.name",
    "org_industry": "org.industry",
    "org_size": "org.size",
    "org_location": "org.location",
    "primary_activities": "org.primary_activities",
    "leadership_roles": "org.leadership_roles",
}


def _format_chunks_for_prompt(chunks: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Format retrieved chunks as evidence text and return citation list."""
    parts = []
    citations = []
    for i, c in enumerate(chunks, 1):
        page = c.get("page", "?")
        filename = c.get("filename", "unknown")
        text = c.get("text", "")
        preamble = c.get("context_preamble", "")
        full_text = f"{preamble}\n\n{text}".strip() if preamble else text
        parts.append(f"[Chunk {i} | {filename}, p.{page}]\n{full_text}")
        citations.append({"chunk": i, "filename": filename, "page": page})
    return "\n\n---\n\n".join(parts), citations


async def _load_org_context(db: Any, tenant_id: str) -> dict[str, str]:
    """Load org profile top-level fields for system prompt."""
    ctx: dict[str, str] = {k: "Not specified" for k in _ORG_FIELDS}
    for var, field_path in _ORG_FIELDS.items():
        doc = await db.org_profile.find_one(
            {"tenant_id": tenant_id, "field_path": field_path}
        )
        if doc and doc.get("value"):
            ctx[var] = str(doc["value"])
    return ctx


async def rag_stream(
    db: Any,
    tenant_id: str,
    question: str,
    history: list[dict[str, str]],
) -> AsyncGenerator[dict[str, Any], None]:
    """Run RAG pipeline and yield SSE-ready event dicts.

    Yields:
        {"type": "token", "content": "<text>"}  — one per streamed token
        {"type": "citations", "citations": [...]}  — after full response
        {"type": "done"}  — final signal
    """
    # 1. Embed question
    try:
        query_vector = await embed_query(question)
    except Exception as exc:
        logger.warning("Embedding failed", error=str(exc))
        query_vector = []

    # 2. Hybrid retrieval
    chunks: list[dict[str, Any]] = []
    if query_vector:
        try:
            chunks = await hybrid_retrieve(db, tenant_id, question, query_vector)
        except Exception as exc:
            logger.warning("Hybrid retrieval failed", error=str(exc))

    evidence_text, citations = _format_chunks_for_prompt(chunks)

    # 3. Load org context
    org_ctx = await _load_org_context(db, tenant_id)

    # 4. Build system prompt
    system_prompt = _jinja.get_template("chat_system.j2").render(**org_ctx)

    # 5. Assemble messages: system + history + current question with evidence
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})

    user_content = question
    if evidence_text:
        user_content = (
            f"{question}\n\n"
            f"--- Retrieved evidence ---\n{evidence_text}"
        )
    messages.append({"role": "user", "content": user_content})

    # 6. Stream LLM response
    logger.info(
        "Chat RAG streaming",
        tenant_id=tenant_id,
        question_len=len(question),
        chunks=len(chunks),
    )

    try:
        async for event in stream(
            model=settings.CHEAP_REASONING_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        ):
            # openai SDK stream yields ChatCompletionChunk objects
            delta = event.choices[0].delta if event.choices else None
            if delta and delta.content:
                yield {"type": "token", "content": delta.content}
    except Exception as exc:
        logger.error("LLM stream failed", error=str(exc))
        yield {"type": "error", "content": str(exc)}
        yield {"type": "done"}
        return

    yield {"type": "citations", "citations": citations}
    yield {"type": "done"}
