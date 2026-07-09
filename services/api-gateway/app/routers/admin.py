"""Admin endpoints — ISO version management.

All routes require the 'admin' role via CurrentAdmin.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from bson import ObjectId
from fastapi import APIRouter, HTTPException, UploadFile, status
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # type: ignore[import-untyped]
from pydantic import BaseModel

from verdeai_shared.auth.tenant import CurrentAdmin
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_state import ISOStateRepository
from verdeai_shared.db.repositories.iso_versions import ISOVersionsRepository
from verdeai_shared.messaging.events import IsoVersionBuildRequested
from verdeai_shared.retrieval.embedder import embed_documents
from verdeai_shared.settings import settings as shared_settings

from app.services.iso_publisher import publish_iso_build_requested


def _pause_key(build_job_id: str) -> str:
    return f"iso_build_pause.{build_job_id}"

router = APIRouter(prefix="/admin", tags=["admin"])

MAX_SOURCE_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class VersionCreate(BaseModel):
    version_id: str
    name: str
    description: str = ""


class VersionSummary(BaseModel):
    version_id: str
    name: str
    description: str
    status: str
    source: str
    clause_count: int
    created_by: str
    created_at: datetime
    published_at: datetime | None = None
    build_job_id: str | None = None
    build_error: str | None = None
    build_status: str = "idle"
    source_docs: list[dict[str, str]] = []


class ClauseCreate(BaseModel):
    clause_id: str
    section: int
    title: str
    requirements: str
    keywords: list[str] = []


class ClauseUpdate(BaseModel):
    title: str | None = None
    requirements: str | None = None
    keywords: list[str] | None = None


class ClauseDetail(BaseModel):
    clause_id: str
    version_id: str
    section: int
    title: str
    requirements: str
    keywords: list[str]


class TemplateFieldUpdate(BaseModel):
    fields: list[dict[str, Any]]  # [{field_path, label, field_type, default}]


class BuildResponse(BaseModel):
    build_job_id: str
    websocket_url: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _version_to_summary(v: dict[str, Any]) -> VersionSummary:
    return VersionSummary(
        version_id=v["version_id"],
        name=v.get("name", ""),
        description=v.get("description", ""),
        status=v.get("status", "draft"),
        source=v.get("source", "manual"),
        clause_count=v.get("clause_count", 0),
        created_by=v.get("created_by", ""),
        created_at=v.get("created_at", datetime.now(timezone.utc)),
        published_at=v.get("published_at"),
        build_job_id=v.get("build_job_id"),
        build_error=v.get("build_error"),
        build_status=v.get("build_status", "idle"),
        source_docs=v.get("source_docs", []),
    )


def _clause_to_detail(c: dict[str, Any]) -> ClauseDetail:
    return ClauseDetail(
        clause_id=c["clause_id"],
        version_id=c.get("version_id", ""),
        section=c.get("section", 0),
        title=c.get("title", ""),
        requirements=c.get("requirements", ""),
        keywords=c.get("keywords", []),
    )


# ---------------------------------------------------------------------------
# Version CRUD
# ---------------------------------------------------------------------------

@router.get("/versions", response_model=list[VersionSummary])
async def list_versions(principal: CurrentAdmin) -> list[VersionSummary]:
    """List all ISO versions (any status)."""
    db = get_database()
    versions = await ISOVersionsRepository(db).list_all()
    return [_version_to_summary(v) for v in versions]


@router.post("/versions", response_model=VersionSummary, status_code=status.HTTP_201_CREATED)
async def create_version(body: VersionCreate, principal: CurrentAdmin) -> VersionSummary:
    """Create a new draft ISO version."""
    db = get_database()
    repo = ISOVersionsRepository(db)

    existing = await repo.get(body.version_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Version '{body.version_id}' already exists")

    doc = {
        "version_id": body.version_id,
        "name": body.name,
        "description": body.description,
        "status": "draft",
        "source": "manual",
        "clause_count": 0,
        "source_docs": [],
        "build_job_id": None,
        "created_by": principal.email,
    }
    await repo.create(doc)
    logger.info("ISO version created", version_id=body.version_id, by=principal.email)
    created = await repo.get(body.version_id)
    return _version_to_summary(created)  # type: ignore[arg-type]


@router.get("/versions/{version_id}", response_model=VersionSummary)
async def get_version(version_id: str, principal: CurrentAdmin) -> VersionSummary:
    db = get_database()
    v = await ISOVersionsRepository(db).get(version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    return _version_to_summary(v)


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(version_id: str, principal: CurrentAdmin) -> None:
    """Delete a draft version (cascade clauses + template). Published versions are archived instead."""
    db = get_database()
    repo = ISOVersionsRepository(db)
    v = await repo.get(version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    if v.get("status") == "published":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a published version. Use /archive instead.",
        )
    # Cascade delete clauses and template
    await ISOClausesRepository(db).delete_for_version(version_id)
    await ISOStateRepository(db).delete_for_version(version_id)
    await repo.delete(version_id)
    logger.info("ISO version deleted", version_id=version_id, by=principal.email)


@router.post("/versions/{version_id}/publish", response_model=VersionSummary)
async def publish_version(version_id: str, principal: CurrentAdmin) -> VersionSummary:
    """Publish a draft version so tenants can use it for analysis."""
    db = get_database()
    repo = ISOVersionsRepository(db)
    v = await repo.get(version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    if v.get("status") not in ("draft",):
        raise HTTPException(status_code=409, detail=f"Version is '{v.get('status')}', not draft")
    if v.get("clause_count", 0) == 0:
        raise HTTPException(status_code=422, detail="Cannot publish a version with no clauses")
    await repo.update_status(version_id, "published")
    logger.info("ISO version published", version_id=version_id, by=principal.email)
    updated = await repo.get(version_id)
    return _version_to_summary(updated)  # type: ignore[arg-type]


@router.post("/versions/{version_id}/archive", response_model=VersionSummary)
async def archive_version(version_id: str, principal: CurrentAdmin) -> VersionSummary:
    """Archive a published version (hides from tenants; keeps history)."""
    db = get_database()
    repo = ISOVersionsRepository(db)
    v = await repo.get(version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    await repo.update_status(version_id, "archived")
    logger.info("ISO version archived", version_id=version_id, by=principal.email)
    updated = await repo.get(version_id)
    return _version_to_summary(updated)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Clause CRUD within a version
# ---------------------------------------------------------------------------

@router.get("/versions/{version_id}/clauses", response_model=list[ClauseDetail])
async def list_clauses(version_id: str, principal: CurrentAdmin) -> list[ClauseDetail]:
    db = get_database()
    await _assert_version_exists(db, version_id)
    clauses = await ISOClausesRepository(db).list_all(version_id=version_id)
    clauses.sort(key=lambda c: (c.get("section", 0), c.get("clause_id", "")))
    return [_clause_to_detail(c) for c in clauses]


@router.get("/versions/{version_id}/clauses/{clause_id}", response_model=ClauseDetail)
async def get_clause(version_id: str, clause_id: str, principal: CurrentAdmin) -> ClauseDetail:
    db = get_database()
    clause = await ISOClausesRepository(db).get(clause_id, version_id=version_id)
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")
    return _clause_to_detail(clause)


@router.post("/versions/{version_id}/clauses", response_model=ClauseDetail, status_code=status.HTTP_201_CREATED)
async def create_clause(version_id: str, body: ClauseCreate, principal: CurrentAdmin) -> ClauseDetail:
    """Manually add a clause to a draft version (embeds on save)."""
    db = get_database()
    v = await _assert_version_exists(db, version_id)
    if v.get("status") == "published":
        raise HTTPException(status_code=409, detail="Cannot add clauses to a published version")

    repo = ISOClausesRepository(db)
    existing = await repo.get(body.clause_id, version_id=version_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Clause '{body.clause_id}' already exists in this version")

    text = f"{body.title}\n{body.requirements}"
    embeddings = await embed_documents([text])

    doc: dict[str, Any] = {
        "version_id": version_id,
        "clause_id": body.clause_id,
        "section": body.section,
        "title": body.title,
        "requirements": body.requirements,
        "keywords": body.keywords,
        "embedding": embeddings[0],
    }
    await repo.upsert(doc)

    # Update clause_count
    count = await repo.count_for_version(version_id)
    await ISOVersionsRepository(db).set_clause_count(version_id, count)

    logger.info("Clause added manually", version_id=version_id, clause_id=body.clause_id)
    return _clause_to_detail(doc)


@router.put("/versions/{version_id}/clauses/{clause_id}", response_model=ClauseDetail)
async def update_clause(version_id: str, clause_id: str, body: ClauseUpdate, principal: CurrentAdmin) -> ClauseDetail:
    """Edit a clause in a draft version (re-embeds if text changed)."""
    db = get_database()
    await _assert_version_exists(db, version_id)
    repo = ISOClausesRepository(db)
    existing = await repo.get(clause_id, version_id=version_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Clause not found")

    updates: dict[str, Any] = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.requirements is not None:
        updates["requirements"] = body.requirements
    if body.keywords is not None:
        updates["keywords"] = body.keywords

    # Re-embed if title or requirements changed
    if "title" in updates or "requirements" in updates:
        title = updates.get("title", existing.get("title", ""))
        reqs = updates.get("requirements", existing.get("requirements", ""))
        embeddings = await embed_documents([f"{title}\n{reqs}"])
        updates["embedding"] = embeddings[0]

    merged = {**existing, **updates, "version_id": version_id, "clause_id": clause_id}
    await repo.upsert(merged)
    logger.info("Clause updated", version_id=version_id, clause_id=clause_id)
    return _clause_to_detail(merged)


@router.delete("/versions/{version_id}/clauses/{clause_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clause(version_id: str, clause_id: str, principal: CurrentAdmin) -> None:
    db = get_database()
    v = await _assert_version_exists(db, version_id)
    if v.get("status") == "published":
        raise HTTPException(status_code=409, detail="Cannot delete clauses from a published version")

    iso_repo = ISOClausesRepository(db)
    existing = await iso_repo.get(clause_id, version_id=version_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Clause not found")

    await db.iso_clauses.delete_one({"version_id": version_id, "clause_id": clause_id})
    await ISOStateRepository(db).delete_for_clause(version_id, clause_id)

    count = await iso_repo.count_for_version(version_id)
    await ISOVersionsRepository(db).set_clause_count(version_id, count)
    logger.info("Clause deleted", version_id=version_id, clause_id=clause_id)


@router.put("/versions/{version_id}/clauses/{clause_id}/template")
async def update_clause_template(
    version_id: str, clause_id: str, body: TemplateFieldUpdate, principal: CurrentAdmin
) -> dict[str, Any]:
    """Replace the state-template fields for a clause."""
    db = get_database()
    await _assert_version_exists(db, version_id)
    state_repo = ISOStateRepository(db)
    await state_repo.delete_for_clause(version_id, clause_id)
    for field in body.fields:
        field["version_id"] = version_id
        field["clause_id"] = clause_id
        await state_repo.upsert(field)
    return {"version_id": version_id, "clause_id": clause_id, "fields": body.fields}


@router.get("/versions/{version_id}/clauses/{clause_id}/template")
async def get_clause_template(version_id: str, clause_id: str, principal: CurrentAdmin) -> dict[str, Any]:
    db = get_database()
    entries = await ISOStateRepository(db).list_for_clause(clause_id, version_id=version_id)
    return {"version_id": version_id, "clause_id": clause_id, "fields": entries}


# ---------------------------------------------------------------------------
# AI Build
# ---------------------------------------------------------------------------

@router.post("/versions/{version_id}/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_source_document(
    version_id: str,
    file: UploadFile,
    principal: CurrentAdmin,
) -> dict[str, str]:
    """Upload a PDF/DOCX source document to use for AI clause extraction."""
    db = get_database()
    v = await _assert_version_exists(db, version_id)
    if v.get("status") not in ("draft",):
        raise HTTPException(status_code=409, detail="Can only upload documents to a draft version")

    data = await file.read()
    if len(data) > MAX_SOURCE_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 100 MB limit")

    filename = file.filename or "document.pdf"
    bucket = AsyncIOMotorGridFSBucket(db)
    gridfs_id = await bucket.upload_from_stream(
        filename, data,
        metadata={"purpose": "iso_source", "version_id": version_id},
    )

    await ISOVersionsRepository(db).append_source_doc(version_id, str(gridfs_id), filename)
    logger.info("Source doc uploaded", version_id=version_id, filename=filename)
    return {"version_id": version_id, "gridfs_id": str(gridfs_id), "filename": filename}


@router.delete("/versions/{version_id}/documents/{gridfs_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_document(version_id: str, gridfs_id: str, principal: CurrentAdmin) -> None:
    """Remove a source document from a draft version."""
    db = get_database()
    v = await _assert_version_exists(db, version_id)
    if v.get("status") != "draft":
        raise HTTPException(status_code=409, detail="Can only remove documents from a draft version")

    # Delete from GridFS
    try:
        bucket = AsyncIOMotorGridFSBucket(db)
        await bucket.delete(ObjectId(gridfs_id))
    except Exception as exc:
        logger.warning("GridFS delete failed (may already be gone)", gridfs_id=gridfs_id, error=str(exc))

    # Remove from source_docs array
    await db.iso_versions.update_one(
        {"version_id": version_id},
        {"$pull": {"source_docs": {"gridfs_id": gridfs_id}}},
    )
    logger.info("Source doc removed", version_id=version_id, gridfs_id=gridfs_id)


@router.post("/versions/{version_id}/build", response_model=BuildResponse)
async def trigger_build(version_id: str, principal: CurrentAdmin) -> BuildResponse:
    """Trigger AI extraction for this version. Streams progress via /ws/jobs/{build_job_id}."""
    db = get_database()
    v = await _assert_version_exists(db, version_id)
    if v.get("status") not in ("draft",):
        raise HTTPException(status_code=409, detail="Can only build a draft version")
    if not v.get("source_docs"):
        raise HTTPException(status_code=422, detail="Upload at least one source document before building")

    build_job_id = str(uuid.uuid4())
    repo = ISOVersionsRepository(db)
    await repo.set_build_job(version_id, build_job_id)
    await repo.set_build_status(version_id, "building")
    await repo.update_status(version_id, "draft", extra={"source": "ai", "build_error": None})

    event = IsoVersionBuildRequested(
        version_id=version_id,
        build_job_id=build_job_id,
        tenant_id=principal.tenant_id,
        source_docs=v.get("source_docs", []),
        requested_by=principal.email,
    )
    try:
        await publish_iso_build_requested(event)
    except Exception as exc:
        logger.error("Failed to publish IsoVersionBuildRequested", error=str(exc))
        raise HTTPException(status_code=502, detail="Failed to queue build job — try again")

    logger.info("ISO build triggered", version_id=version_id, build_job_id=build_job_id, by=principal.email)
    return BuildResponse(build_job_id=build_job_id, websocket_url=f"/ws/jobs/{build_job_id}")


# ---------------------------------------------------------------------------
# Build reset (clears stuck/dead build_job_id so the button re-enables)
# ---------------------------------------------------------------------------

@router.post("/versions/{version_id}/build/reset")
async def reset_build(version_id: str, principal: CurrentAdmin) -> dict[str, str]:
    """Clear a stuck or dead build job so the admin can re-trigger."""
    db = get_database()
    await _assert_version_exists(db, version_id)
    repo = ISOVersionsRepository(db)
    await repo.set_build_job(version_id, "")
    await repo.set_build_status(version_id, "idle")
    return {"status": "reset"}


# ---------------------------------------------------------------------------
# Build pause / resume
# ---------------------------------------------------------------------------

@router.post("/versions/{version_id}/build/pause")
async def pause_build(version_id: str, principal: CurrentAdmin) -> dict[str, str]:
    """Signal the running build pipeline to pause after the current batch."""
    db = get_database()
    v = await _assert_version_exists(db, version_id)
    build_job_id: str | None = v.get("build_job_id")
    if not build_job_id:
        raise HTTPException(status_code=422, detail="No build job associated with this version")

    r: aioredis.Redis = aioredis.from_url(shared_settings.REDIS_URL)  # type: ignore[type-arg]
    try:
        await r.set(_pause_key(build_job_id), "1", ex=3600)
    finally:
        await r.aclose()

    logger.info("Build pause requested", version_id=version_id, build_job_id=build_job_id)
    return {"status": "pause_requested", "build_job_id": build_job_id}


@router.post("/versions/{version_id}/build/resume", response_model=BuildResponse)
async def resume_build(version_id: str, principal: CurrentAdmin) -> BuildResponse:
    """Resume a paused build. Assigns a new build_job_id and re-queues the pipeline."""
    db = get_database()
    v = await _assert_version_exists(db, version_id)

    if v.get("build_status") != "paused":
        raise HTTPException(status_code=422, detail="Build is not paused")
    if not v.get("source_docs"):
        raise HTTPException(status_code=422, detail="No source documents found")

    old_job_id: str | None = v.get("build_job_id")
    new_job_id = str(uuid.uuid4())

    # Clear the old pause signal (belt-and-suspenders)
    r: aioredis.Redis = aioredis.from_url(shared_settings.REDIS_URL)  # type: ignore[type-arg]
    try:
        if old_job_id:
            await r.delete(_pause_key(old_job_id))
    finally:
        await r.aclose()

    repo = ISOVersionsRepository(db)
    await repo.set_build_job(version_id, new_job_id)
    await repo.clear_build_checkpoint(version_id)  # sets build_status = "building"

    event = IsoVersionBuildRequested(
        version_id=version_id,
        build_job_id=new_job_id,
        tenant_id=principal.tenant_id,
        source_docs=v.get("source_docs", []),
        requested_by=principal.email,
    )
    try:
        await publish_iso_build_requested(event)
    except Exception as exc:
        logger.error("Failed to publish resume event", error=str(exc))
        raise HTTPException(status_code=502, detail="Failed to queue resume — try again")

    logger.info("Build resumed", version_id=version_id, new_job_id=new_job_id, by=principal.email)
    return BuildResponse(build_job_id=new_job_id, websocket_url=f"/ws/jobs/{new_job_id}")


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _assert_version_exists(db: Any, version_id: str) -> dict[str, Any]:
    v = await ISOVersionsRepository(db).get(version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    return v
