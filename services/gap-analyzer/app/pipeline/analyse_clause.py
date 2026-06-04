"""Per-clause gap analysis pipeline.

For each ISO clause:
  1. Embed clause as query → vector search + BM25 hybrid retrieval
  2. Load org_profile + state_template for this clause
  3. Call state_compare LLM → state_diff
  4. Call gap_analyse LLM → decision / confidence / citations
  5. Persist to result_store
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import verdeai_shared as _vs_pkg
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from verdeai_shared.db.repositories.iso_state import ISOStateRepository
from verdeai_shared.db.repositories.result_store import ResultStoreRepository
from verdeai_shared.llm.openrouter_client import stream_with_reasoning
from verdeai_shared.retrieval.embedder import embed_query
from verdeai_shared.retrieval.hybrid import hybrid_retrieve
from verdeai_shared.settings import settings

_PROMPTS_DIR = Path(_vs_pkg.__file__).parent / "llm" / "prompts"


class AnalysisPaused(Exception):
    """Raised when a pause flag is detected mid-clause."""
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_INSUFFICIENT = {
    "decision": "Insufficient Evidence",
    "confidence": 0.0,
    "reasoning": "No relevant document chunks found in the tenant knowledge base for this clause.",
    "citations": [],
    "missing_evidence": ["Upload and process relevant compliance documents to enable gap analysis."],
}


def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        page = c.get("page", "?")
        text = c.get("text", "")
        parts.append(f"[Chunk {i} | Page {page}]\n{text}")
    return "\n\n---\n\n".join(parts)


async def analyse_clause(
    db: Any,
    tenant_id: str,
    analysis_id: str,
    clause: dict[str, Any],
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Run the full analysis pipeline for one ISO clause. Returns gap result dict."""
    clause_id: str = clause["clause_id"]
    clause_title: str = clause.get("title", clause_id)

    # 1. Embed clause text as a search query
    query_text = f"{clause_title}\n{clause.get('requirements', '')}"
    try:
        query_vector = await embed_query(query_text)
    except Exception as exc:
        logger.warning("Embedding failed for clause", clause_id=clause_id, error=str(exc))
        query_vector = []

    # 2. Hybrid retrieval
    chunks: list[dict[str, Any]] = []
    if query_vector:
        try:
            chunks = await hybrid_retrieve(db, tenant_id, query_text, query_vector)
        except Exception as exc:
            logger.warning("Hybrid retrieval failed", clause_id=clause_id, error=str(exc))

    if not chunks:
        logger.info("No chunks retrieved — insufficient evidence", clause_id=clause_id)
        result = dict(_INSUFFICIENT)
        await ResultStoreRepository(db, tenant_id).upsert(analysis_id, clause_id, result)
        return result

    evidence_text = _format_chunks(chunks)

    # 3. Load org_profile for this clause
    org_cursor = db.org_profile.find(
        {"tenant_id": tenant_id, "field_path": {"$regex": f"^{clause_id}\\."}}
    )
    org_entries = await org_cursor.to_list(None)
    org_profile_map = {e["field_path"]: e.get("value") for e in org_entries}

    # 4. Load state template for this clause
    state_entries = await ISOStateRepository(db).list_for_clause(clause_id)
    state_template_list = [
        {"field_path": e["field_path"], "label": e.get("label"), "field_type": e.get("field_type"), "default": e.get("default")}
        for e in state_entries
    ]

    # 5. state_compare LLM call (streams reasoning tokens to on_thinking callback)
    state_diff: dict[str, Any] = {}
    try:
        tmpl = _jinja.get_template("state_compare.j2")
        prompt = tmpl.render(
            clause_id=clause_id,
            clause_title=clause_title,
            org_profile_json=json.dumps(org_profile_map, indent=2),
            state_template_json=json.dumps(state_template_list, indent=2),
            evidence_chunks=evidence_text,
        )
        answer = await stream_with_reasoning(
            model=settings.PRIMARY_REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.0,
            response_format={"type": "json_object"},
            on_thinking=on_thinking,
        )
        state_diff = json.loads(answer)
    except Exception as exc:
        logger.warning("state_compare LLM call failed", clause_id=clause_id, error=str(exc))

    # Pause check between the two LLM calls
    status_doc = await db.analyses.find_one({"analysis_id": analysis_id}, {"status": 1})
    if status_doc and status_doc.get("status") == "paused":
        raise AnalysisPaused(analysis_id)

    # 6. gap_analyse LLM call (streams reasoning tokens to on_thinking callback)
    gap_result: dict[str, Any] = {}
    try:
        tmpl = _jinja.get_template("gap_analyse.j2")
        prompt = tmpl.render(
            clause_id=clause_id,
            clause_title=clause_title,
            state_diff_json=json.dumps(state_diff.get("state_diff", {}), indent=2),
            reference_context_json=json.dumps(state_diff.get("reference_context", {}), indent=2),
            evidence_chunks=evidence_text,
        )
        answer = await stream_with_reasoning(
            model=settings.PRIMARY_REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.0,
            response_format={"type": "json_object"},
            on_thinking=on_thinking,
        )
        gap_result = json.loads(answer)
    except Exception as exc:
        logger.warning("gap_analyse LLM call failed", clause_id=clause_id, error=str(exc))
        gap_result = dict(_INSUFFICIENT)
        gap_result["reasoning"] = f"LLM call failed: {exc}"

    # 7. Persist to result_store
    await ResultStoreRepository(db, tenant_id).upsert(analysis_id, clause_id, gap_result)

    logger.info(
        "Clause analysed",
        clause_id=clause_id,
        decision=gap_result.get("decision"),
        confidence=gap_result.get("confidence"),
    )
    return gap_result
