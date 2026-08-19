"""Chat RAG pipeline — retrieval, context assembly, and LLM streaming."""

from __future__ import annotations

import json
import re
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

_ORG_CONTEXT_KEYS = ("org_name", "org_industry", "org_size", "org_location", "description")
_DETAIL_RESULT_LIMIT = 8
_ANALYSIS_CONTEXT_MAX_CHARS = 24_000
_DECISION_PRIORITY = {"Not Met": 0, "Partially Met": 1, "Insufficient Evidence": 2, "Met": 3}


# ── Tracked wrappers for granular Langfuse tracing ──────────────────
@observe(name="embed_query")  # type: ignore[misc]
async def _tracked_embed_query(text: str) -> list[float]:
    """Traced wrapper around Voyage embed_query."""
    return await embed_query(text)


@observe(name="hybrid_retrieve")  # type: ignore[misc]
async def _tracked_hybrid_retrieve(
    db: Any, tenant_id: str, profile_id: str, question: str, query_vector: list[float]
) -> list[dict[str, Any]]:
    """Traced wrapper around hybrid retrieval (vector + BM25 + rerank)."""
    return await hybrid_retrieve(db, tenant_id, profile_id, question, query_vector)


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
        source_key = f"document-{i}"
        page = c.get("page", "?")
        filename = c.get("filename", "unknown")
        text = c.get("text", "")
        preamble = c.get("context_preamble", "")
        full_text = f"{preamble}\n\n{text}".strip() if preamble else text
        parts.append(f"[Source {source_key} | {filename}, p.{page}]\n{full_text}")
        citations.append({
            "type": "document",
            "source_key": source_key,
            "display_label": f"{filename} · p.{page}",
            "chunk": i,
            "filename": filename,
            "page": page,
            "text": full_text,  # included so the frontend can show the excerpt on click
        })
    return "\n\n---\n\n".join(parts), citations


@observe(name="load_org_context")  # type: ignore[misc]
async def _load_org_context(db: Any, tenant_id: str, profile_id: str) -> dict[str, str]:
    """Load the selected org profile's fields for the system prompt."""
    from verdeai_shared.db.repositories.org_profiles import OrgProfilesRepository

    profile = await OrgProfilesRepository(db, tenant_id).get(profile_id) or {}
    return {key: str(profile.get(key) or "Not specified") for key in _ORG_CONTEXT_KEYS}


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


async def load_chat_context(db: Any, tenant_id: str, profile_id: str) -> dict[str, Any]:
    """Return public metadata for the analysis currently authoritative in chat."""
    analysis = await db.analyses.find_one(
        {"tenant_id": tenant_id, "profile_id": profile_id, "status": "complete"},
        sort=[("created_at", -1)],
    )
    if not analysis:
        active = await db.analyses.find_one(
            {
                "tenant_id": tenant_id,
                "profile_id": profile_id,
                "status": {"$in": ["pending", "running", "paused"]},
            },
            sort=[("created_at", -1)],
        )
        return {
            "has_completed_analysis": False,
            "analysis_id": None,
            "newer_analysis_status": active.get("status") if active else None,
            "stale": False,
            "new_chunk_count": 0,
            "removed_chunk_count": 0,
        }

    baseline = analysis.get("created_at")
    chunk_filter = {
        "tenant_id": tenant_id,
        "profile_id": profile_id,
        "created_at": {"$gt": baseline},
        "superseded": {"$ne": True},
    }
    new_chunk_count = await db.chunks.count_documents(chunk_filter) if baseline else 0
    removed_chunk_count = await db.chunks.count_documents({
        "tenant_id": tenant_id,
        "profile_id": profile_id,
        "superseded": True,
        "superseded_at": {"$gt": baseline},
    }) if baseline else 0
    active = await db.analyses.find_one(
        {
            "tenant_id": tenant_id,
            "profile_id": profile_id,
            "status": {"$in": ["pending", "running", "paused"]},
            "created_at": {"$gt": baseline},
        },
        sort=[("created_at", -1)],
    ) if baseline else None

    return {
        "has_completed_analysis": True,
        "analysis_id": str(analysis.get("analysis_id", analysis.get("_id", ""))),
        "created_at": _iso(baseline),
        "version_id": analysis.get("version_id", "iso-14001-2015"),
        "scope": analysis.get("scope", "full"),
        "gap_count": analysis.get("gap_count", 0),
        "mode": analysis.get("mode", "full"),
        "stale": bool(new_chunk_count or removed_chunk_count),
        "new_chunk_count": new_chunk_count,
        "removed_chunk_count": removed_chunk_count,
        "newer_analysis_status": active.get("status") if active else None,
    }


def _result_search_text(result: dict[str, Any], recs: list[dict[str, Any]], missing: list[dict[str, Any]]) -> str:
    clause_id = str(result.get("clause_id", ""))
    values = [clause_id, result.get("reasoning", ""), *result.get("missing_evidence", [])]
    values += [
        value
        for fill in result.get("slot_fills", [])
        for value in (fill.get("slot_id", ""), fill.get("state", ""), fill.get("value", ""), fill.get("notes", ""))
    ]
    values += [
        value
        for slot in result.get("slot_schema", [])
        for value in (slot.get("label", ""), slot.get("question", ""))
    ]
    values += [r.get("text", "") for r in recs if str(r.get("clause_id", "")) == clause_id]
    values += [m.get("request_text", "") for m in missing if str(m.get("clause_id", "")) == clause_id]
    return " ".join(str(v) for v in values).lower()


def _select_detailed_results(
    question: str,
    results: list[dict[str, Any]],
    recs: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select detailed clauses deterministically while retaining a compact overview of all."""
    q = question.lower()
    clause_mentions = set(re.findall(r"\b(?:clause\s*)?(\d+(?:\.\d+)+)\b", q))
    mentioned = [r for r in results if str(r.get("clause_id", "")) in clause_mentions]
    if mentioned:
        return mentioned[:_DETAIL_RESULT_LIMIT]

    tokens = {t for t in re.findall(r"[a-z0-9]+", q) if len(t) > 3}
    ranked: list[tuple[int, int, float, str, dict[str, Any]]] = []
    for result in results:
        searchable = _result_search_text(result, recs, missing)
        overlap = sum(1 for token in tokens if token in searchable)
        decision = str(result.get("decision", "Unknown"))
        clause_id = str(result.get("clause_id", ""))
        related_recs = [r for r in recs if str(r.get("clause_id", "")) == clause_id]
        impact = max((float(r.get("impact", 0) or 0) for r in related_recs), default=0.0)
        ranked.append((-overlap, _DECISION_PRIORITY.get(decision, 4), -impact, clause_id, result))
    ranked.sort(key=lambda item: item[:4])
    return [item[4] for item in ranked[:_DETAIL_RESULT_LIMIT]]


def _normalise_analysis_citations(
    metadata: dict[str, Any], detailed: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for result in detailed:
        clause_id = str(result.get("clause_id", "?"))
        safe_clause_id = re.sub(r"[^a-zA-Z0-9.-]+", "-", clause_id)
        analysis_source_key = f"analysis-{safe_clause_id}"
        analysis_citation = {
            "type": "analysis",
            "source_key": analysis_source_key,
            "display_label": f"Clause {clause_id} · {result.get('decision', 'Unknown')}",
            "analysis_id": metadata["analysis_id"],
            "clause_id": clause_id,
            "decision": result.get("decision", "Unknown"),
            "version_id": metadata.get("version_id"),
            "created_at": metadata.get("created_at"),
            "text": result.get("reasoning", ""),
        }
        citations.append(analysis_citation)
        document_number = 0
        for raw in result.get("citations", []):
            if raw.get("type") != "chunk" or not raw.get("filename"):
                continue
            document_number += 1
            source_key = f"{analysis_source_key}-document-{document_number}"
            citations.append({
                "type": "document",
                "source_key": source_key,
                "display_label": f"{raw.get('filename', 'unknown')} · p.{raw.get('page', '?')}",
                "filename": raw.get("filename", "unknown"),
                "page": raw.get("page", "?"),
                "text": raw.get("text", ""),
                "analysis_id": metadata["analysis_id"],
                "clause_id": clause_id,
            })
    return citations


@observe(name="load_analysis_context")  # type: ignore[misc]
async def _load_analysis_context(
    db: Any, tenant_id: str, profile_id: str, question: str
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Build authoritative, budgeted context from the latest completed analysis."""
    metadata = await load_chat_context(db, tenant_id, profile_id)
    if not metadata["has_completed_analysis"]:
        return "", [], metadata

    analysis_id = metadata["analysis_id"]

    # Load all gap results for this analysis
    cursor = db.result_store.find({"tenant_id": tenant_id, "analysis_id": analysis_id})
    results: list[dict[str, Any]] = await cursor.to_list(length=None)

    rec_cursor = db.recommendation_store.find({"tenant_id": tenant_id, "analysis_id": analysis_id})
    recs: list[dict[str, Any]] = await rec_cursor.to_list(length=None)
    missing_cursor = db.missing_request_store.find({"tenant_id": tenant_id, "analysis_id": analysis_id})
    missing: list[dict[str, Any]] = await missing_cursor.to_list(length=None)
    detailed = _select_detailed_results(question, results, recs, missing)

    rows: list[str] = []
    for r in sorted(results, key=lambda x: x.get("clause_id", "")):
        clause_id = r.get("clause_id", "?")
        decision = r.get("decision", "Unknown")
        confidence = r.get("confidence", 0.0)
        gaps = r.get("missing_evidence", [])
        gap_str = str(gaps[0]) if gaps else "-"
        rows.append(
            f"  Clause {clause_id}: {decision} (confidence {confidence:.0%})"
            + (f"\n    Gaps: {gap_str}" if gaps else "")
        )

    lines = [
        "== AUTHORITATIVE LATEST COMPLETED GAP ANALYSIS ==",
        f"Analysis ID: {analysis_id}",
        f"Completed: {metadata.get('created_at')} | ISO version: {metadata.get('version_id')} | "
        f"Scope: {metadata.get('scope')} | Total gaps: {metadata.get('gap_count')}",
        f"Stale: {metadata.get('stale')} | New evidence chunks: {metadata.get('new_chunk_count')} | "
        f"Removed evidence chunks: {metadata.get('removed_chunk_count')}",
        "",
        "Complete clause decision overview:",
        *rows,
        "",
        "Detailed clauses selected for this question:",
    ]
    for result in detailed:
        clause_id = str(result.get("clause_id", "?"))
        safe_clause_id = re.sub(r"[^a-zA-Z0-9.-]+", "-", clause_id)
        analysis_source_key = f"analysis-{safe_clause_id}"
        lines += [
            f"\n[Source {analysis_source_key} | Analysis {analysis_id} | Clause {clause_id}]",
            f"Decision: {result.get('decision', 'Unknown')} | Confidence: {float(result.get('confidence', 0) or 0):.0%}",
            f"Reasoning: {result.get('reasoning', '')}",
            "Missing evidence: " + ("; ".join(str(g) for g in result.get("missing_evidence", [])) or "None recorded"),
        ]
        findings = result.get("findings", [])
        if findings:
            lines.append("Sub-requirement findings:")
            lines += [
                f"- {f.get('req_id', '?')}: {f.get('status', 'unknown')} — {f.get('notes', '')}"
                for f in findings
            ]
        slot_fills = result.get("slot_fills", [])
        slot_schema = {
            str(slot.get("slot_id", "")): slot for slot in result.get("slot_schema", [])
        }
        if slot_fills:
            lines.append("Requirement slot evidence:")
            for fill in slot_fills:
                slot_id = str(fill.get("slot_id", "?"))
                slot = slot_schema.get(slot_id, {})
                label = slot.get("label") or slot_id
                value = fill.get("value") or fill.get("notes") or "No value recorded"
                lines.append(f"- {label}: {fill.get('state', 'unknown')} — {value}")
        children_summary = result.get("children_summary")
        if children_summary:
            lines.append(f"Sub-clause aggregation: {children_summary}")
        persisted_citations = [
            c for c in result.get("citations", [])
            if c.get("type") == "chunk" and c.get("filename")
        ]
        if persisted_citations:
            lines.append("Grounded evidence citations:")
            lines += [
                f"- [Source {analysis_source_key}-document-{i} | {c.get('filename')}, p.{c.get('page', '?')}]: {c.get('text', '')}"
                for i, c in enumerate(persisted_citations, 1)
            ]
        related_recs = [r for r in recs if str(r.get("clause_id", "")) == clause_id]
        if related_recs:
            lines.append("Recommendations:")
            lines += [
                f"- {r.get('text', '')} (cost {r.get('cost', '?')}/5, effort {r.get('effort_weeks', '?')}w, impact {r.get('impact', '?')}/5)"
                for r in related_recs
            ]
        related_missing = [m for m in missing if str(m.get("clause_id", "")) == clause_id]
        if related_missing:
            lines.append("Information requests:")
            lines += [f"- {m.get('request_text', '')}" for m in related_missing]

    context = "\n".join(lines)
    return context[:_ANALYSIS_CONTEXT_MAX_CHARS], _normalise_analysis_citations(metadata, detailed), metadata


@observe(name="chat")  # type: ignore[misc]
async def rag_stream(
    db: Any,
    tenant_id: str,
    profile_id: str,
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

    # 1. Resolve the authoritative analysis before retrieving supporting documents.
    try:
        analysis_context, analysis_citations, chat_context = await _load_analysis_context(
            db, tenant_id, profile_id, question
        )
    except Exception as exc:
        logger.warning("Failed to load analysis context", error=str(exc))
        analysis_context, analysis_citations = "", []
        chat_context = {"has_completed_analysis": False, "stale": False}

    # 2. Retrieve fresh chunks only as supporting evidence when a completed
    # analysis exists. Without one, chat must not silently perform an ad-hoc audit.
    query_vector: list[float] = []
    if chat_context["has_completed_analysis"]:
        try:
            query_vector = await _tracked_embed_query(question)
        except Exception as exc:
            logger.warning("Embedding failed", error=str(exc))

    chunks: list[dict[str, Any]] = []
    if query_vector:
        try:
            chunks = await _tracked_hybrid_retrieve(db, tenant_id, profile_id, question, query_vector)
        except Exception as exc:
            logger.warning("Hybrid retrieval failed", error=str(exc))

    # Enrich chunks with filenames (chunks only store document_id)
    try:
        chunks = await _enrich_chunks_with_filenames(db, tenant_id, chunks)
    except Exception as exc:
        logger.warning("Failed to enrich chunk filenames", error=str(exc))

    evidence_text, document_citations = _format_chunks_for_prompt(chunks)
    citations = analysis_citations + document_citations

    # 3. Load org context
    try:
        org_ctx = await _load_org_context(db, tenant_id, profile_id)
    except Exception as exc:
        logger.warning("Failed to load org context", error=str(exc))
        org_ctx = {k: "Not specified" for k in _ORG_CONTEXT_KEYS}

    # 4. Build system prompt with explicit analysis availability/freshness.
    system_prompt = _jinja.get_template("chat_system.j2").render(
        **org_ctx,
        has_completed_analysis=chat_context["has_completed_analysis"],
        analysis_stale=chat_context.get("stale", False),
        analysis_id=chat_context.get("analysis_id"),
    )

    # 6. Assemble messages: system + history + current question with evidence
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})

    user_content = question
    context_sections: list[str] = []
    if analysis_context:
        context_sections.append(
            f"<authoritative_gap_analysis>\n{analysis_context}\n</authoritative_gap_analysis>"
        )
    if evidence_text:
        context_sections.append(
            "<supporting_document_evidence>\n"
            "This evidence may explain the stored verdict, but must not be used to replace it.\n"
            f"{evidence_text}\n</supporting_document_evidence>"
        )
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
        analysis_id=chat_context.get("analysis_id"),
        analysis_stale=chat_context.get("stale", False),
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
