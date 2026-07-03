"""Chat RAG pipeline — retrieval, context assembly, and LLM streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import verdeai_shared as _vs_pkg
from bson import ObjectId
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from verdeai_shared.llm.openrouter_client import stream
from verdeai_shared.retrieval.embedder import embed_query
from verdeai_shared.retrieval.hybrid import hybrid_retrieve
from verdeai_shared.settings import settings

try:
    from langfuse.decorators import langfuse_context, observe  # type: ignore[import-untyped]
    _LANGFUSE = True
except ImportError:
    _LANGFUSE = False
    def observe(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore[misc]
        return lambda fn: fn

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


# ── Tracked wrappers for granular Langfuse tracing ──────────────────
@observe(name="embed_query")  # type: ignore[misc]
async def _tracked_embed_query(text: str) -> list[float]:
    """Traced wrapper around Voyage embed_query."""
    return await embed_query(text)


@observe(name="hybrid_retrieve")  # type: ignore[misc]
async def _tracked_hybrid_retrieve(
    db: Any, tenant_id: str, question: str, query_vector: list[float]
) -> list[dict[str, Any]]:
    """Traced wrapper around hybrid retrieval (vector + BM25 + rerank)."""
    return await hybrid_retrieve(db, tenant_id, question, query_vector)


async def _enrich_chunks_with_filenames(
    db: Any, tenant_id: str, chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fetch filenames from the documents collection and attach them to chunks.

    Chunks only store document_id; the filename lives in the documents collection.
    """
    doc_ids = [c.get("document_id") for c in chunks if c.get("document_id")]
    if not doc_ids:
        return chunks

    try:
        object_ids = [ObjectId(d) for d in doc_ids]
    except Exception:
        return chunks

    cursor = db.documents.find(
        {"tenant_id": tenant_id, "_id": {"$in": object_ids}},
        {"_id": 1, "filename": 1},
    )
    docs = await cursor.to_list(length=None)
    id_to_filename = {str(d["_id"]): d.get("filename", "unknown") for d in docs}

    enriched = []
    for chunk in chunks:
        c = dict(chunk)
        c["filename"] = id_to_filename.get(str(c.get("document_id", "")), "unknown")
        enriched.append(c)
    return enriched


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
        citations.append({
            "chunk": i,
            "filename": filename,
            "page": page,
            "text": full_text,  # included so the frontend can show the excerpt on click
        })
    return "\n\n---\n\n".join(parts), citations


@observe(name="load_org_context")  # type: ignore[misc]
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


@observe(name="load_analysis_context")  # type: ignore[misc]
async def _load_analysis_context(db: Any, tenant_id: str) -> str:
    """Load the latest gap analysis results and recommendations for the tenant.

    Returns a formatted text block ready to be injected into the prompt, or an
    empty string if no analysis has been run yet.
    """
    # Find most recent analysis run for this tenant
    analysis = await db.analyses.find_one(
        {"tenant_id": tenant_id},
        sort=[("_id", -1)],
    )
    if not analysis:
        return ""

    analysis_id = str(analysis.get("analysis_id", analysis.get("_id", "")))
    status = analysis.get("status", "unknown")
    gap_count = analysis.get("gap_count")

    header_parts = [f"Status: {status}"]
    if gap_count is not None:
        header_parts.append(f"Total gaps found: {gap_count}")

    # Load all gap results for this analysis
    cursor = db.result_store.find({"tenant_id": tenant_id, "analysis_id": analysis_id})
    results: list[dict[str, Any]] = await cursor.to_list(length=None)

    if not results:
        return f"== Latest Gap Analysis ==\n{' | '.join(header_parts)}\nNo clause results available yet.\n"

    # Build compact clause table
    rows: list[str] = []
    for r in sorted(results, key=lambda x: x.get("clause_id", "")):
        clause_id = r.get("clause_id", "?")
        decision = r.get("decision", "Unknown")
        confidence = r.get("confidence", 0.0)
        gaps = r.get("missing_evidence", [])
        gap_str = "; ".join(gaps[:2]) if gaps else "-"
        rows.append(
            f"  Clause {clause_id}: {decision} (confidence {confidence:.0%})"
            + (f"\n    Gaps: {gap_str}" if gaps else "")
        )

    # Load recommendations
    rec_cursor = db.recommendation_store.find(
        {"tenant_id": tenant_id, "analysis_id": analysis_id}
    )
    recs: list[dict[str, Any]] = await rec_cursor.to_list(length=None)
    rec_lines: list[str] = []
    for rec in recs:
        clause_id = rec.get("clause_id", "?")
        text = rec.get("text", "")
        cost = rec.get("cost", "?")
        effort = rec.get("effort_weeks", "?")
        impact = rec.get("impact", "?")
        rec_lines.append(
            f"  Clause {clause_id}: {text} "
            f"(Cost {cost}/5, Effort {effort}w, Impact {impact}/5)"
        )

    lines = [
        "== Latest Gap Analysis ==",
        " | ".join(header_parts),
        "",
        "Clause compliance decisions:",
        *rows,
    ]
    if rec_lines:
        lines += ["", "Recommendations:", *rec_lines]

    return "\n".join(lines)


@observe(name="chat")  # type: ignore[misc]
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
    if _LANGFUSE:
        try:
            langfuse_context.update_current_trace(
                session_id=tenant_id,
                user_id=tenant_id,
                tags=["chat"],
            )
        except Exception:
            pass

    # 1. Embed question
    try:
        query_vector = await _tracked_embed_query(question)
    except Exception as exc:
        logger.warning("Embedding failed", error=str(exc))
        query_vector = []

    # 2. Hybrid retrieval
    chunks: list[dict[str, Any]] = []
    if query_vector:
        try:
            chunks = await _tracked_hybrid_retrieve(db, tenant_id, question, query_vector)
        except Exception as exc:
            logger.warning("Hybrid retrieval failed", error=str(exc))

    # Enrich chunks with filenames (chunks only store document_id)
    try:
        chunks = await _enrich_chunks_with_filenames(db, tenant_id, chunks)
    except Exception as exc:
        logger.warning("Failed to enrich chunk filenames", error=str(exc))

    evidence_text, citations = _format_chunks_for_prompt(chunks)

    # 3. Load org context
    try:
        org_ctx = await _load_org_context(db, tenant_id)
    except Exception as exc:
        logger.warning("Failed to load org context", error=str(exc))
        org_ctx = {k: "Not specified" for k in _ORG_FIELDS}

    # 4. Load gap analysis context (latest analysis results + recommendations)
    try:
        analysis_context = await _load_analysis_context(db, tenant_id)
    except Exception as exc:
        logger.warning("Failed to load analysis context", error=str(exc))
        analysis_context = ""

    # 5. Build system prompt
    system_prompt = _jinja.get_template("chat_system.j2").render(**org_ctx)

    # 6. Assemble messages: system + history + current question with evidence
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})

    user_content = question
    context_sections: list[str] = []
    if evidence_text:
        context_sections.append(f"--- Retrieved document evidence ---\n{evidence_text}")
    if analysis_context:
        context_sections.append(analysis_context)
    if context_sections:
        user_content = question + "\n\n" + "\n\n".join(context_sections)
    messages.append({"role": "user", "content": user_content})

    # 7. Stream LLM response
    logger.info(
        "Chat RAG streaming",
        tenant_id=tenant_id,
        question_len=len(question),
        chunks=len(chunks),
        has_analysis=bool(analysis_context),
    )

    try:
        async for event in stream(
            model=settings.CHAT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
            name="chat",
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
