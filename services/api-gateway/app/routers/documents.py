"""Document management endpoints."""

import hashlib
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # type: ignore[import-untyped]

from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.org_profiles import OrgProfilesRepository
from verdeai_shared.messaging.events import DocumentDeleted, DocumentUploaded

from app.schemas.documents import (
    DocumentDeleteResponse,
    DocumentItem,
    DocumentListResponse,
    DocumentUploadResponse,
)
from app.services.document_publisher import publish_document_deleted, publish_document_uploaded

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    principal: CurrentPrincipal,
    profile_id: str = Query(...),
) -> DocumentUploadResponse:
    """Upload a document for processing, scoped to one org profile."""
    tenant_id = principal.tenant_id
    db = get_database()

    if await OrgProfilesRepository(db, tenant_id).get(profile_id) is None:
        raise HTTPException(status_code=404, detail="Org profile not found")

    # Read and size-check
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 100 MB limit")

    filename = file.filename or "unknown"
    sha256 = hashlib.sha256(data).hexdigest()

    # Check for duplicate (same sha256 for this tenant + profile, ignoring deleted docs)
    existing = await db.documents.find_one({
        "tenant_id": tenant_id, "profile_id": profile_id, "sha256": sha256, "status": {"$ne": "deleted"}
    })
    if existing is not None:
        doc_id = str(existing["_id"])
        logger.info("Dedup hit — returning existing document", document_id=doc_id)
        await db.documents.update_one(
            {"_id": existing["_id"]},
            {"$set": {"status": "deduped"}},
        )
        return DocumentUploadResponse(
            document_id=doc_id,
            status="deduped",
            websocket_url=f"/ws/jobs/{doc_id}",
        )

    # Store raw file in GridFS
    bucket = AsyncIOMotorGridFSBucket(db)
    gridfs_id = await bucket.upload_from_stream(filename, data)

    # Insert document record
    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": tenant_id,
        "profile_id": profile_id,
        "filename": filename,
        "sha256": sha256,
        "status": "queued",
        "pages": None,
        "docling_blob_ref": None,
        "summary": None,
        "gridfs_id": gridfs_id,
        "created_at": now,
    }
    result = await db.documents.insert_one(doc)
    document_id = str(result.inserted_id)

    # Publish event
    event = DocumentUploaded(
        tenant_id=tenant_id,
        profile_id=profile_id,
        document_id=document_id,
        filename=filename,
        sha256=sha256,
    )
    try:
        await publish_document_uploaded(event)
    except Exception as exc:
        logger.error("Failed to publish document.uploaded event", error=str(exc))
        # Still return 202 — the event can be retried via reconciliation

    logger.info("Document queued", document_id=document_id, filename=filename)
    return DocumentUploadResponse(
        document_id=document_id,
        status="queued",
        websocket_url=f"/ws/jobs/{document_id}",
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    principal: CurrentPrincipal,
    status: str | None = Query(default=None),
    profile_id: str | None = Query(default=None),
) -> DocumentListResponse:
    """List documents for the current tenant, optionally scoped to one org profile."""
    tenant_id = principal.tenant_id
    db = get_database()

    query: dict[str, object] = {"tenant_id": tenant_id}
    if status:
        query["status"] = status
    if profile_id:
        query["profile_id"] = profile_id

    cursor = db.documents.find(query, sort=[("created_at", -1)], limit=200)
    docs = await cursor.to_list(length=None)

    items = [
        DocumentItem(
            document_id=str(d["_id"]),
            profile_id=d.get("profile_id", ""),
            filename=d.get("filename", ""),
            status=d.get("status", "unknown"),
            pages=d.get("pages"),
            uploaded_at=d.get("created_at", datetime.now(timezone.utc)),
            previous_version_id=d.get("previous_version_id"),
            cdc_overlap=d.get("cdc_overlap"),
        )
        for d in docs
    ]
    return DocumentListResponse(items=items)


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    principal: CurrentPrincipal,
) -> dict[str, object]:
    """Get a single document record."""
    tenant_id = principal.tenant_id
    db = get_database()

    try:
        oid = ObjectId(document_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    doc = await db.documents.find_one({"_id": oid, "tenant_id": tenant_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    doc["document_id"] = str(doc.pop("_id"))
    doc.pop("gridfs_id", None)
    return doc  # type: ignore[return-value]


@router.delete("/{document_id}", response_model=DocumentDeleteResponse, status_code=202)
async def delete_document(
    document_id: str,
    principal: CurrentPrincipal,
) -> DocumentDeleteResponse:
    """Soft-delete a document and queue chunk cleanup."""
    tenant_id = principal.tenant_id
    db = get_database()

    try:
        oid = ObjectId(document_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    doc = await db.documents.find_one({"_id": oid, "tenant_id": tenant_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.documents.update_one({"_id": oid}, {"$set": {"status": "deleted"}})

    event = DocumentDeleted(tenant_id=tenant_id, profile_id=doc["profile_id"], document_id=document_id)
    try:
        await publish_document_deleted(event)
    except Exception as exc:
        logger.error("Failed to publish document.deleted event", error=str(exc))

    return DocumentDeleteResponse(status="deletion_queued")
