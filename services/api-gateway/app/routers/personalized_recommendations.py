"""Web-grounded personalized recommendation run endpoints."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError
from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.org_profiles import OrgProfilesRepository
from verdeai_shared.db.repositories.personalized_recommendation_runs import (
    PersonalizedRecommendationRunsRepository,
)
from verdeai_shared.messaging.events import PersonalizedRecommendationRequested

from app.services.personalized_recommendation_publisher import (
    publish_personalized_recommendation_requested,
)

router = APIRouter(prefix="/personalized-recommendations", tags=["personalized-recommendations"])

_PROFILE_FIELDS = ("org_name", "org_industry", "description", "org_location")


class CreateRunRequest(BaseModel):
    profile_id: str


def _public(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    return {key: value for key, value in doc.items() if key != "_id" and key != "tenant_id"}


def _recommendation_key(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get("text", "")).split()).lower()
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    return f"{row.get('clause_id', 'unknown')}:{digest}"


async def _load_context(db: Any, tenant_id: str, profile_id: str) -> dict[str, Any]:
    profile = await OrgProfilesRepository(db, tenant_id).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Org profile not found")

    missing_fields = [
        field for field in _PROFILE_FIELDS
        if not str(profile.get(field) or "").strip()
    ]
    latest = await db.analyses.find_one(
        {"tenant_id": tenant_id, "profile_id": profile_id},
        sort=[("created_at", -1)],
    )
    completed = await db.analyses.find_one(
        {"tenant_id": tenant_id, "profile_id": profile_id, "status": "complete"},
        sort=[("created_at", -1)],
    )
    active_run = await PersonalizedRecommendationRunsRepository(
        db, tenant_id
    ).find_active(profile_id)

    result: dict[str, Any] = {
        "profile": _public(profile),
        "profile_id": profile_id,
        "profile_complete": not missing_fields,
        "missing_profile_fields": missing_fields,
        "latest_analysis": _public(completed),
        "newer_analysis": None,
        "staleness": {"stale": False, "new_chunk_count": 0, "removed_chunk_count": 0},
        "baseline_recommendation_count": 0,
        "baseline_recommendation_status": "unavailable",
        "can_generate": False,
        "blocked_reason": None,
        "active_run": _public(active_run),
    }

    if completed is not None:
        completed_at = completed.get("created_at") or datetime.now(UTC)
        if latest and latest.get("analysis_id") != completed.get("analysis_id"):
            result["newer_analysis"] = _public(latest)

        chunk_base = {"tenant_id": tenant_id, "profile_id": profile_id}
        new_count = await db.chunks.count_documents({
            **chunk_base,
            "superseded": {"$ne": True},
            "created_at": {"$gt": completed_at},
        })
        removed_count = await db.chunks.count_documents({
            **chunk_base,
            "superseded": True,
            "superseded_at": {"$gt": completed_at},
        })
        result["staleness"] = {
            "stale": bool(new_count or removed_count),
            "new_chunk_count": new_count,
            "removed_chunk_count": removed_count,
        }

        rec_count = await db.recommendation_store.count_documents({
            "tenant_id": tenant_id,
            "analysis_id": completed["analysis_id"],
        })
        lifecycle = completed.get("recommendation_status")
        if lifecycle is None:
            lifecycle = (
                "complete"
                if rec_count or completed.get("gap_count") == 0
                else "unavailable"
            )
        result["baseline_recommendation_count"] = rec_count
        result["baseline_recommendation_status"] = lifecycle

    if missing_fields:
        result["blocked_reason"] = "profile_incomplete"
    elif completed is None:
        result["blocked_reason"] = "analysis_required"
    elif completed.get("gap_count") == 0:
        result["blocked_reason"] = "no_actionable_gaps"
    elif result["baseline_recommendation_count"] == 0:
        result["blocked_reason"] = "baseline_recommendations_unavailable"
    elif result["baseline_recommendation_status"] in {"pending", "running"}:
        result["blocked_reason"] = "baseline_recommendations_processing"
    elif active_run is not None:
        result["blocked_reason"] = "run_active"
    else:
        result["can_generate"] = True
    return result


@router.get("/context", response_model=dict[str, Any])
async def get_context(
    principal: CurrentPrincipal,
    profile_id: str = Query(...),
) -> dict[str, Any]:
    return await _load_context(get_database(), principal.tenant_id, profile_id)


@router.get("", response_model=list[dict[str, Any]])
async def list_runs(
    principal: CurrentPrincipal,
    profile_id: str = Query(...),
) -> list[dict[str, Any]]:
    db = get_database()
    if await OrgProfilesRepository(db, principal.tenant_id).get(profile_id) is None:
        raise HTTPException(status_code=404, detail="Org profile not found")
    rows = await PersonalizedRecommendationRunsRepository(
        db, principal.tenant_id
    ).list_for_profile(profile_id)
    return [_public(row) or {} for row in rows]


@router.post("", response_model=dict[str, Any], status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    body: CreateRunRequest,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    tenant_id = principal.tenant_id
    db = get_database()
    context = await _load_context(db, tenant_id, body.profile_id)
    if not context["can_generate"]:
        raise HTTPException(
            status_code=409 if context["blocked_reason"] == "run_active" else 422,
            detail={
                "code": context["blocked_reason"],
                "missing_fields": context["missing_profile_fields"],
            },
        )

    analysis = context["latest_analysis"]
    analysis_id = analysis["analysis_id"]
    rec_cursor = db.recommendation_store.find(
        {"tenant_id": tenant_id, "analysis_id": analysis_id},
        sort=[("clause_id", 1), ("created_at", 1)],
    )
    baseline_rows = await rec_cursor.to_list(length=None)
    baseline_recommendations = [
        {
            "recommendation_key": _recommendation_key(row),
            "clause_id": row.get("clause_id", ""),
            "text": row.get("text", ""),
            "cost": row.get("cost", 0),
            "effort_weeks": row.get("effort_weeks", 0),
            "impact": row.get("impact", 0),
        }
        for row in baseline_rows
    ]
    gap_cursor = db.result_store.find({
        "tenant_id": tenant_id,
        "analysis_id": analysis_id,
        "decision": {"$nin": ["Met", "Insufficient Evidence"]},
    })
    gap_rows = await gap_cursor.to_list(length=None)
    gaps = [
        {
            "clause_id": row.get("clause_id", ""),
            "decision": row.get("decision", ""),
            "reasoning": row.get("reasoning", ""),
            "missing_evidence": row.get("missing_evidence", []),
            "findings": row.get("findings", []),
        }
        for row in gap_rows
    ]
    profile_cursor = db.org_profile.find({
        "tenant_id": tenant_id,
        "profile_id": body.profile_id,
        "version_id": analysis.get("version_id"),
    })
    structured_profile = {
        row["field_path"]: row.get("value")
        for row in await profile_cursor.to_list(length=None)
        if row.get("value") not in (None, "", [])
    }
    profile_snapshot = {
        key: value for key, value in (context["profile"] or {}).items()
        if key in {"org_name", "org_industry", "org_size", "org_location", "description"}
    }
    profile_snapshot["structured_fields"] = structured_profile

    run_id = str(uuid.uuid4())
    repo = PersonalizedRecommendationRunsRepository(db, tenant_id)
    try:
        await repo.create({
            "run_id": run_id,
            "profile_id": body.profile_id,
            "analysis_id": analysis_id,
            "version_id": analysis.get("version_id"),
            "analysis_created_at": analysis.get("created_at"),
            "profile_snapshot": profile_snapshot,
            "gaps": gaps,
            "baseline_recommendations": baseline_recommendations,
            "limits": {},
        })
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail={"code": "run_active"}) from exc
    event = PersonalizedRecommendationRequested(
        tenant_id=tenant_id,
        profile_id=body.profile_id,
        analysis_id=analysis_id,
        run_id=run_id,
    )
    try:
        await publish_personalized_recommendation_requested(event)
    except Exception as exc:
        await db.personalized_recommendation_runs.delete_one({
            "tenant_id": tenant_id,
            "run_id": run_id,
        })
        raise HTTPException(status_code=502, detail="Failed to queue research — try again") from exc
    return {"run_id": run_id, "status": "queued"}


@router.get("/{run_id}", response_model=dict[str, Any])
async def get_run(run_id: str, principal: CurrentPrincipal) -> dict[str, Any]:
    row = await PersonalizedRecommendationRunsRepository(
        get_database(), principal.tenant_id
    ).get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Recommendation run not found")
    return _public(row) or {}
