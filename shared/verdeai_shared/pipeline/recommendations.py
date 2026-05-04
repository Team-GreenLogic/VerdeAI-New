"""Shared recommendation generation pipeline (used by gap-analyzer inline + recommendation service)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import verdeai_shared as _vs_pkg
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.recommendation_store import RecommendationStoreRepository
from verdeai_shared.llm.openrouter_client import complete
from verdeai_shared.settings import settings

_PROMPTS_DIR = Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def generate_recommendations(
    db: Any,
    tenant_id: str,
    analysis_id: str,
    gap_result: dict[str, Any],
) -> None:
    """Generate 2-4 recommendations for a gap clause and persist them.

    Idempotent: skips if recommendations already exist for this analysis_id + clause_id.
    """
    clause_id: str = gap_result["clause_id"]

    # Idempotency check
    existing = await db.recommendation_store.find_one(
        {"tenant_id": tenant_id, "analysis_id": analysis_id, "clause_id": clause_id}
    )
    if existing:
        logger.debug("Recommendations already exist — skipping", clause_id=clause_id)
        return

    # Load clause details for title
    clause = await ISOClausesRepository(db).get(clause_id)
    clause_title = clause.get("title", clause_id) if clause else clause_id

    # Load org_profile entries for this clause
    org_cursor = db.org_profile.find(
        {"tenant_id": tenant_id, "field_path": {"$regex": f"^{clause_id}\\."}}
    )
    org_entries = await org_cursor.to_list(None)
    org_profile_map = {e["field_path"]: e.get("value") for e in org_entries}

    # Render prompt
    tmpl = _jinja.get_template("recommend.j2")
    prompt = tmpl.render(
        clause_id=clause_id,
        clause_title=clause_title,
        decision=gap_result.get("decision", "Not Met"),
        failing_assertions_json=json.dumps(gap_result.get("missing_evidence", [])),
        reference_context_json=json.dumps(org_profile_map),
        actionable_seeds_json="[]",
    )

    try:
        resp = await complete(
            model=settings.PRIMARY_REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = json.loads(resp.choices[0].message.content)
        # LLM may return {"recommendations": [...]} or directly [...]
        if isinstance(raw, list):
            recs = raw
        else:
            recs = raw.get("recommendations", list(raw.values())[0] if raw else [])
    except Exception as exc:
        logger.warning("Recommendation LLM call failed", clause_id=clause_id, error=str(exc))
        return

    tagged = [{**r, "clause_id": clause_id} for r in recs if isinstance(r, dict)]
    if tagged:
        await RecommendationStoreRepository(db, tenant_id).insert_many(analysis_id, tagged)
        logger.info("Persisted recommendations", clause_id=clause_id, count=len(tagged))
