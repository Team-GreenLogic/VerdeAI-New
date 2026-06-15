"""Shared missing-requirement request generation pipeline (used by gap-analyzer inline + missing-requirements service)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import verdeai_shared as _vs_pkg
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_state import ISOStateRepository
from verdeai_shared.db.repositories.missing_request_store import MissingRequestStoreRepository
from verdeai_shared.llm.openrouter_client import complete
from verdeai_shared.settings import settings

_PROMPTS_DIR = Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_MAX_FIELDS_PER_CLAUSE = 5
_DEFAULT_RESPONSIBLE_ROLE = "Environmental Management Representative"


async def generate_missing_requests(
    db: Any,
    tenant_id: str,
    analysis_id: str,
    gap_result: dict[str, Any],
) -> None:
    """Draft information-request messages for each missing state field and persist them.

    Idempotent: skips if requests already exist for this analysis_id + clause_id.
    """
    clause_id: str = gap_result["clause_id"]

    # Idempotency check
    existing = await db.missing_request_store.find_one(
        {"tenant_id": tenant_id, "analysis_id": analysis_id, "clause_id": clause_id}
    )
    if existing:
        logger.debug("Missing requests already exist — skipping", clause_id=clause_id)
        return

    # Load clause details for title
    clause = await ISOClausesRepository(db).get(clause_id)
    clause_title = clause.get("title", clause_id) if clause else clause_id

    # Load state template fields (cap to avoid excessive LLM calls)
    state_entries = await ISOStateRepository(db).list_for_clause(clause_id)
    fields = state_entries[:_MAX_FIELDS_PER_CLAUSE]

    if not fields:
        logger.info("No state fields found for clause", clause_id=clause_id)
        return

    items: list[dict[str, Any]] = []
    system_prompt = _jinja.get_template("draft_request_system.j2").render()
    user_tmpl = _jinja.get_template("draft_request_user.j2")

    for field in fields:
        field_path = field.get("field_path", "")
        field_description = field.get("label", field_path)

        user_prompt = user_tmpl.render(
            clause_id=clause_id,
            clause_title=clause_title,
            field_path=field_path,
            field_description=field_description,
            responsible_role=_DEFAULT_RESPONSIBLE_ROLE,
        )

        try:
            resp = await complete(
                model=settings.CHEAP_REASONING_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=256,
                temperature=0.3,
            )
            request_text = resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning(
                "draft_request LLM call failed",
                clause_id=clause_id,
                field_path=field_path,
                error=str(exc),
            )
            continue

        items.append({
            "clause_id": clause_id,
            "field_path": field_path,
            "request_text": request_text,
        })

    if items:
        await MissingRequestStoreRepository(db, tenant_id).insert_many(analysis_id, items)
        logger.info("Persisted missing requests", clause_id=clause_id, count=len(items))
