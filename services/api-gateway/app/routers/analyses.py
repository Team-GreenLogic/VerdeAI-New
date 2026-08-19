"""Gap analysis endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from loguru import logger
from pydantic import BaseModel

from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID, ISOVersionsRepository
from verdeai_shared.messaging.events import AnalysisRequested

from app.services.analysis_publisher import publish_analysis_requested
from app.services.report_builder import build_report_context, render_report_pdf

router = APIRouter(prefix="/analyses", tags=["analyses"])

_ACTIVE_STATUSES = ("pending", "running")


class AnalysisSummary(BaseModel):
    analysis_id: str
    status: str
    gap_count: int | None
    scope: Any
    version_id: str = DEFAULT_VERSION_ID
    created_at: datetime
    mode: str = "full"
    parent_analysis_id: str | None = None
    # How many clauses were attempted, and how many failed to analyse. Without these a run
    # where most clauses errored is indistinguishable from a clean one: status is "complete"
    # either way and gap_count alone cannot tell a gap from a crash.
    clause_total: int | None = None
    error_count: int = 0


class StalenessResponse(BaseModel):
    stale: bool
    new_chunk_count: int
    removed_chunk_count: int


class DeltaReanalyzeResponse(BaseModel):
    analysis_id: str
    parent_analysis_id: str
    status: str


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
    # What the evidence established per ISO requirement slot, and the findings derived from
    # it. The decision above follows from these states — see docs/gap-analysis.md §2.1.
    # Defaulted: results predating the slot layer, and the Insufficient Evidence abstain
    # path, carry neither.
    slot_fills: list[dict[str, Any]] = []
    slot_schema: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    # The arithmetic behind the decision (coverage, bands, critical failures) and whether the
    # evidence it ran on was complete. Both defaulted: results predating them carry neither.
    decision_trace: dict[str, Any] = {}
    evidence_status: str = ""
    # For a title-only clause (ISO 14001's 6.1, 6.2, 7.4, 7.5, 9.1, 9.2 — headings with no
    # normative text of their own): pooled coverage + each child's real slot fills, grouped
    # by sub-clause. Never a fabricated schema of this clause's own — slot_fills/slot_schema
    # above stay empty for these rows. None for an ordinary, independently-analysed clause.
    children_summary: dict[str, Any] | None = None


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
            mode=r.get("mode", "full"),
            parent_analysis_id=r.get("parent_analysis_id"),
            clause_total=r.get("clause_total"),
            error_count=r.get("error_count", 0),
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


@router.get("/{analysis_id}/staleness", response_model=StalenessResponse)
async def get_staleness(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> StalenessResponse:
    """Report whether the tenant's evidence has changed since this analysis ran.

    Powers the "New uploads detected" banner: counts chunks ingested after the
    analysis baseline (new evidence) and chunks superseded after it (removed /
    modified evidence). Either kind makes the analysis potentially out of date.
    """
    tenant_id = principal.tenant_id
    db = get_database()
    doc = await _get_owned(db, analysis_id, tenant_id)
    baseline = doc.get("created_at", datetime.now(timezone.utc))

    new_chunk_count = await db.chunks.count_documents({
        "tenant_id": tenant_id,
        "superseded": {"$ne": True},
        "created_at": {"$gt": baseline},
    })
    removed_chunk_count = await db.chunks.count_documents({
        "tenant_id": tenant_id,
        "superseded": True,
        "superseded_at": {"$gt": baseline},
    })

    return StalenessResponse(
        stale=(new_chunk_count > 0 or removed_chunk_count > 0),
        new_chunk_count=new_chunk_count,
        removed_chunk_count=removed_chunk_count,
    )


@router.post(
    "/{analysis_id}/reanalyze-delta",
    response_model=DeltaReanalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reanalyze_delta(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> DeltaReanalyzeResponse:
    """Start an incremental re-analysis of only the clauses affected by evidence
    added or removed since the parent analysis. Creates a new versioned analysis
    that copies unaffected verdicts forward from the parent."""
    tenant_id = principal.tenant_id
    db = get_database()

    parent = await _get_owned(db, analysis_id, tenant_id)
    if parent.get("status") != "complete":
        raise HTTPException(
            status_code=409,
            detail="Delta re-analysis is only available for a completed analysis "
                   f"(current status: '{parent.get('status', 'unknown')}').",
        )

    await _assert_no_active(db, tenant_id)

    new_analysis_id = str(uuid.uuid4())
    baseline_at = parent.get("created_at", datetime.now(timezone.utc))
    version_id = parent.get("version_id", DEFAULT_VERSION_ID)
    scope = parent.get("scope", "full")
    now = datetime.now(timezone.utc)

    await db.analyses.insert_one({
        "analysis_id": new_analysis_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "version_id": version_id,
        "status": "pending",
        "gap_count": None,
        "created_at": now,
        "mode": "delta",
        "parent_analysis_id": analysis_id,
        "baseline_at": baseline_at,
    })

    event = AnalysisRequested(
        tenant_id=tenant_id,
        analysis_id=new_analysis_id,
        scope=scope,
        version_id=version_id,
        mode="delta",
        parent_analysis_id=analysis_id,
        baseline_at=baseline_at,
    )
    try:
        await publish_analysis_requested(event)
    except Exception as exc:
        logger.error("Failed to publish delta AnalysisRequested", error=str(exc))
        await db.analyses.delete_one({"analysis_id": new_analysis_id})
        raise HTTPException(status_code=502, detail="Failed to queue delta analysis — try again")

    logger.info(
        "Delta analysis queued",
        analysis_id=new_analysis_id,
        parent_analysis_id=analysis_id,
        tenant_id=tenant_id,
    )
    return DeltaReanalyzeResponse(
        analysis_id=new_analysis_id,
        parent_analysis_id=analysis_id,
        status="pending",
    )


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
            slot_fills=r.get("slot_fills", []),
            slot_schema=r.get("slot_schema", []),
            findings=r.get("findings", []),
            decision_trace=r.get("decision_trace", {}),
            evidence_status=r.get("evidence_status", ""),
            children_summary=r.get("children_summary"),
        )
        for r in rows
    ]


@router.get("/{analysis_id}/report.pdf")
async def download_report(
    analysis_id: str,
    principal: CurrentPrincipal,
) -> Response:
    """Generate and download a print-ready PDF compliance report for a completed analysis."""
    tenant_id = principal.tenant_id
    db = get_database()

    doc = await _get_owned(db, analysis_id, tenant_id)
    if doc.get("status") != "complete":
        raise HTTPException(
            status_code=409,
            detail=f"Report is only available once the analysis is complete "
                   f"(current status: '{doc.get('status', 'unknown')}').",
        )

    try:
        context = await build_report_context(db, tenant_id, doc)
        pdf_bytes = render_report_pdf(context)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to generate compliance report", analysis_id=analysis_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to generate compliance report")

    filename = f"compliance-report-{analysis_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
