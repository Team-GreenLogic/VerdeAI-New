"""Shared recommendation generation pipeline (used by gap-analyzer inline + recommendation service)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import verdeai_shared as _vs_pkg
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID
from verdeai_shared.db.repositories.recommendation_store import RecommendationStoreRepository
from verdeai_shared.llm.openrouter_client import complete
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


@observe(name="recommendation")  # type: ignore[misc]
async def generate_recommendations(
    db: Any,
    tenant_id: str,
    analysis_id: str,
    gap_result: dict[str, Any],
    version_id: str = DEFAULT_VERSION_ID,
) -> None:
    """Generate 2-4 recommendations for a gap clause and persist them.

    Idempotent: skips if recommendations already exist for this analysis_id + clause_id.
    """
    clause_id: str = gap_result["clause_id"]

    if _LANGFUSE:
        try:
            langfuse_context.update_current_trace(
                session_id=tenant_id,
                user_id=tenant_id,
                tags=["recommendation", clause_id],
                metadata={"analysis_id": analysis_id, "clause_id": clause_id},
            )
        except Exception:
            pass

    # Idempotency check
    existing = await db.recommendation_store.find_one(
        {"tenant_id": tenant_id, "analysis_id": analysis_id, "clause_id": clause_id}
    )
    if existing:
        logger.debug("Recommendations already exist — skipping", clause_id=clause_id)
        return

    # Load clause details for title
    clause = await ISOClausesRepository(db).get(clause_id, version_id=version_id)
    clause_title = clause.get("title", clause_id) if clause else clause_id

    # Load org_profile entries for this clause
    org_cursor = db.org_profile.find(
        {"tenant_id": tenant_id, "field_path": {"$regex": f"^{clause_id}\\."}}
    )
    org_entries = await org_cursor.to_list(None)
    org_profile_map = {e["field_path"]: e.get("value") for e in org_entries}

    # recommend_system.j2 requires every recommendation to cite a specific failing item, so
    # an empty list would leave it nothing to anchor to. The gap analyser only lists evidence
    # genuinely needed to adjudicate the clause, so a non-Met clause can legitimately have an
    # empty missing_evidence — fall back to the findings that actually failed.
    failing_items = gap_result.get("missing_evidence") or [
        f"{f.get('req_id', '')}: {f.get('notes', '')}".strip(": ")
        for f in gap_result.get("findings", [])
        if f.get("status") in ("unmet", "partial")
    ]

    # Render prompt
    system_prompt = _jinja.get_template("recommend_system.j2").render()
    user_prompt = _jinja.get_template("recommend_user.j2").render(
        clause_id=clause_id,
        clause_title=clause_title,
        decision=gap_result.get("decision", "Not Met"),
        failing_assertions_json=json.dumps(failing_items),
        reference_context_json=json.dumps(org_profile_map),
        actionable_seeds_json="[]",
    )

    content: str = ""
    try:
        resp = await complete(
            model=settings.PRIMARY_REASONING_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=1024,
            temperature=0.0,
            response_format={"type": "json_object"},
            name="recommendation",
        )
        content = resp.choices[0].message.content or ""
        raw = json.loads(content)
        # Prompt asks for {"recommendations": [...]} to match response_format=json_object
        # (a bare JSON array is invalid under that mode); keep the list fallback defensively
        # in case a model ignores the object-wrapping instruction.
        if isinstance(raw, list):
            recs = raw
        elif isinstance(raw, dict):
            recs = raw.get("recommendations", [])
        else:
            recs = []
    except Exception as exc:
        logger.warning(
            "Recommendation LLM call failed",
            clause_id=clause_id,
            error=str(exc),
            raw_response=content[:300],
        )
        return

    tagged = [{**r, "clause_id": clause_id} for r in recs if isinstance(r, dict)]
    if tagged:
        await RecommendationStoreRepository(db, tenant_id).insert_many(analysis_id, tagged)
        logger.info("Persisted recommendations", clause_id=clause_id, count=len(tagged))
