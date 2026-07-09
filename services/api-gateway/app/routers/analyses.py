"""Gap analysis endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID, ISOVersionsRepository
from verdeai_shared.messaging.events import AnalysisRequested

from app.services.analysis_publisher import publish_analysis_requested

router = APIRouter(prefix="/analyses", tags=["analyses"])

_ACTIVE_STATUSES = ("pending", "running")


class AnalysisSummary(BaseModel):
    analysis_id: str
    status: str
    gap_count: int | None
    scope: Any
    version_id: str = DEFAULT_VERSION_ID
    created_at: datetime


class VersionItem(BaseModel):
    version_id: str
    name: str
    description: str


class AnalysisCreateRequest(BaseModel):
    scope: Literal["full"] | dict[str, list[str]] = "full"
    version_id: str = DEFAULT_VERSION_ID


class AnalysisCreateResponse(BaseModel):
    analysis_id: str
    status: str


class GapResult(BaseModel):
    clause_id: str
    decision: str
    confidence: float
    reasoning: str
    citations: list[dict[str, Any]]
    missing_evidence: list[str]


class RecommendationItem(BaseModel):
    clause_id: str
    text: str
    cost: int
    effort_weeks: float
    impact: int


class MissingRequirementItem(BaseModel):
    clause_id: str
    field_path: str
    request_text: str


async def _get_owned(db: Any, analysis_id: str, tenant_id: str) -> dict[str, Any]:
    """Fetch analysis doc, raise 404 if not found or not owned by tenant."""
    doc = await db.analyses.find_one({"analysis_id": analysis_id, "tenant_id": tenant_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return doc


async def _assert_no_active(db: Any, tenant_id: str) -> None:
    """Raise 409 if any analysis is currently pending or running for this tenant."""
    active = await db.analyses.find_one(
        {"tenant_id": tenant_id, "status": {"$in": list(_ACTIVE_STATUSES)}}
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"Analysis {active['analysis_id']} is already {active['status']}. "
                   "Pause or wait for it to complete before starting a new one.",
        )


@router.get("/versions", response_model=list[VersionItem])
async def list_published_versions(principal: CurrentPrincipal) -> list[VersionItem]:
    """Return all published ISO versions available for analysis."""
    db = get_database()
    versions = await ISOVersionsRepository(db).list_published()
    return [
        VersionItem(
            version_id=v["version_id"],
            name=v.get("name", v["version_id"]),
            description=v.get("description", ""),
        )
        for v in versions
    ]


@router.get("", response_model=list[AnalysisSummary])
async def list_analyses(principal: CurrentPrincipal) -> list[AnalysisSummary]:
    """List all analyses for the current tenant, newest first."""
    tenant_id = principal.tenant_id
    db = get_database()
    cursor = db.analyses.find(
        {"tenant_id": tenant_id},
        sort=[("created_at", -1)],
        limit=50,
    )
    rows = await cursor.to_list(length=None)
    return [
        AnalysisSummary(
            analysis_id=r["analysis_id"],
            status=r.get("status", "unknown"),
            gap_count=r.get("gap_count"),
            scope=r.get("scope"),
            version_id=r.get("version_id", DEFAULT_VERSION_ID),
            created_at=r.get("created_at", datetime.now(timezone.utc)),
        )
        for r in rows
    ]


@router.post("", response_model=AnalysisCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    body: AnalysisCreateRequest,
    principal: CurrentPrincipal,
) -> AnalysisCreateResponse:
    """Trigger a new gap analysis. Returns 409 if one is already running."""
    tenant_id = principal.tenant_id
    db = get_database()

    await _assert_no_active(db, tenant_id)

    # Validate that the requested version is published
    version_id = body.version_id
    version_doc = await ISOVersionsRepository(db).get(version_id)
    if not version_doc or version_doc.get("status") != "published":
        raise HTTPException(
            status_code=422,
            detail=f"ISO version '{version_id}' is not available. Choose a published version.",
        )

    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.analyses.insert_one({
        "analysis_id": analysis_id,
        "tenant_id": tenant_id,
        "scope": body.scope,
        "version_id": version_id,
        "status": "pending",
        "gap_count": None,
        "created_at": now,
    })

    event = AnalysisRequested(
        tenant_id=tenant_id,
        analysis_id=analysis_id,
        scope=body.scope,
        version_id=version_id,
    )
    try:
        await publish_analysis_requested(event)
    except Exception as exc:
        logger.error("Failed to publish AnalysisRequested", error=str(exc))
        await db.analyses.delete_one({"analysis_id": analysis_id})
        raise HTTPException(status_code=502, detail="Failed to queue analysis — try again")

    logger.info("Analysis queued", analysis_id=analysis_id, tenant_id=tenant_id)
    return AnalysisCreateResponse(analysis_id=analysis_id, status="pending")


@router.post("/{analysis_id}/pause", status_code=status.HTTP_200_OK)
async def pause_analysis(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> dict[str, str]:
    """Pause a pending or running analysis. Takes effect before the next clause."""
    tenant_id = principal.tenant_id
    db = get_database()

    doc = await _get_owned(db, analysis_id, tenant_id)
    if doc["status"] not in _ACTIVE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pause an analysis with status '{doc['status']}'.",
        )

    await db.analyses.update_one(
        {"analysis_id": analysis_id, "tenant_id": tenant_id},
        {"$set": {"status": "paused"}},
    )
    logger.info("Analysis paused", analysis_id=analysis_id)
    return {"analysis_id": analysis_id, "status": "paused"}


@router.post("/{analysis_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_analysis(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> dict[str, str]:
    """Resume a paused analysis. Returns 409 if another analysis is already active."""
    tenant_id = principal.tenant_id
    db = get_database()

    doc = await _get_owned(db, analysis_id, tenant_id)
    if doc["status"] != "paused":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resume an analysis with status '{doc['status']}'.",
        )

    # Ensure no other analysis is already running
    other_active = await db.analyses.find_one({
        "tenant_id": tenant_id,
        "analysis_id": {"$ne": analysis_id},
        "status": {"$in": list(_ACTIVE_STATUSES)},
    })
    if other_active:
        raise HTTPException(
            status_code=409,
            detail=f"Analysis {other_active['analysis_id']} is already {other_active['status']}.",
        )

    await db.analyses.update_one(
        {"analysis_id": analysis_id, "tenant_id": tenant_id},
        {"$set": {"status": "pending"}},
    )

    event = AnalysisRequested(
        tenant_id=tenant_id,
        analysis_id=analysis_id,
        scope=doc["scope"],
        version_id=doc.get("version_id", DEFAULT_VERSION_ID),
    )
    try:
        await publish_analysis_requested(event)
    except Exception as exc:
        logger.error("Failed to re-publish AnalysisRequested on resume", error=str(exc))
        await db.analyses.update_one(
            {"analysis_id": analysis_id, "tenant_id": tenant_id},
            {"$set": {"status": "paused"}},
        )
        raise HTTPException(status_code=502, detail="Failed to resume analysis — try again")

    logger.info("Analysis resumed", analysis_id=analysis_id)
    return {"analysis_id": analysis_id, "status": "pending"}


@router.get("/{analysis_id}", response_model=dict[str, Any])
async def get_analysis(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    """Get analysis status and summary."""
    tenant_id = principal.tenant_id
    db = get_database()
    doc = await _get_owned(db, analysis_id, tenant_id)
    doc.pop("_id", None)
    return doc


@router.get("/{analysis_id}/results", response_model=list[GapResult])
async def get_analysis_results(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> list[GapResult]:
    """Get per-clause gap analysis results."""
    tenant_id = principal.tenant_id
    db = get_database()

    await _get_owned(db, analysis_id, tenant_id)

    cursor = db.result_store.find(
        {"analysis_id": analysis_id, "tenant_id": tenant_id},
        sort=[("clause_id", 1)],
    )
    rows = await cursor.to_list(length=None)

    return [
        GapResult(
            clause_id=r["clause_id"],
            decision=r.get("decision", "Unknown"),
            confidence=r.get("confidence", 0.0),
            reasoning=r.get("reasoning", ""),
            citations=r.get("citations", []),
            missing_evidence=r.get("missing_evidence", []),
        )
        for r in rows
    ]


@router.get("/{analysis_id}/recommendations", response_model=list[RecommendationItem])
async def get_recommendations(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> list[RecommendationItem]:
    """Get per-clause recommendations generated after gap analysis."""
    tenant_id = principal.tenant_id
    db = get_database()

    await _get_owned(db, analysis_id, tenant_id)

    cursor = db.recommendation_store.find(
        {"analysis_id": analysis_id, "tenant_id": tenant_id},
        sort=[("clause_id", 1)],
    )
    rows = await cursor.to_list(length=None)

    return [
        RecommendationItem(
            clause_id=r["clause_id"],
            text=r.get("text", ""),
            cost=r.get("cost", 0),
            effort_weeks=r.get("effort_weeks", 0),
            impact=r.get("impact", 0),
        )
        for r in rows
    ]


@router.get("/{analysis_id}/missing-requirements", response_model=list[MissingRequirementItem])
async def get_missing_requirements(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> list[MissingRequirementItem]:
    """Get missing-requirement request drafts generated after gap analysis."""
    tenant_id = principal.tenant_id
    db = get_database()

    await _get_owned(db, analysis_id, tenant_id)

    cursor = db.missing_request_store.find(
        {"analysis_id": analysis_id, "tenant_id": tenant_id},
        sort=[("clause_id", 1)],
    )
    rows = await cursor.to_list(length=None)

    return [
        MissingRequirementItem(
            clause_id=r["clause_id"],
            field_path=r.get("field_path", ""),
            request_text=r.get("request_text", ""),
        )
        for r in rows
    ]
