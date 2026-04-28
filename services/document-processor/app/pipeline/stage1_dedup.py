"""Stage 1 — Dedup gate.

Checks SHA-256 for exact-duplicate detection.
Computes FastCDC chunk hashes on raw bytes for near-duplicate (modified doc) detection.
pHash (image pages) is deferred to Phase 2 when Docling is available.
"""

import hashlib
from io import BytesIO

from fastcdc import fastcdc  # type: ignore[import-untyped]
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # type: ignore[import-untyped]

from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.hash_store import HashStoreRepository

from app.progress import emit

# FastCDC settings (avg 4 KB, min 2 KB, max 8 KB)
CDC_AVG = 4096
CDC_MIN = 2048
CDC_MAX = 8192


async def run(tenant_id: str, document_id: str, sha256: str) -> str:
    """Run dedup stage. Returns final status: 'deduped' or 'parsed' (next stage)."""
    db = get_database()
    hash_repo = HashStoreRepository(db, tenant_id)

    await emit(tenant_id, document_id, "dedup", "running", "Checking for duplicates")

    # --- SHA-256 exact dedup ---
    existing = await hash_repo.find_by_sha256(sha256)
    if existing is not None:
        existing_doc_id: str = existing.get("document_id", "")
        # If the hash_store record points to this same document it means the
        # pipeline is being retried after a downstream failure — not a real dup.
        if existing_doc_id == document_id:
            logger.info(
                "Pipeline retry detected — skipping dedup gate",
                tenant_id=tenant_id,
                document_id=document_id,
            )
        else:
            logger.info(
                "Exact duplicate detected",
                tenant_id=tenant_id,
                document_id=document_id,
                original_doc_id=existing_doc_id,
            )
            await db.documents.update_one(
                {"_id": __import__("bson").ObjectId(document_id)},
                {"$set": {"status": "deduped", "deduped_from": existing_doc_id}},
            )
            await emit(tenant_id, document_id, "dedup", "deduped",
                       f"Exact duplicate of {existing_doc_id}")
            await emit(tenant_id, document_id, "complete", "done", "")
            return "deduped"

    # --- Fetch raw bytes from GridFS ---
    doc = await db.documents.find_one(
        {"_id": __import__("bson").ObjectId(document_id), "tenant_id": tenant_id}
    )
    if doc is None:
        raise RuntimeError(f"Document {document_id} not found in DB")

    gridfs_id = doc.get("gridfs_id")
    if gridfs_id is None:
        raise RuntimeError(f"Document {document_id} has no gridfs_id")

    bucket = AsyncIOMotorGridFSBucket(db)
    buf = BytesIO()
    await bucket.download_to_stream(gridfs_id, buf)
    raw_bytes = buf.getvalue()

    # --- FastCDC chunk hashes for near-duplicate detection ---
    cdc_hashes = _compute_fastcdc_hashes(raw_bytes)

    # --- Check for modified version (>50% chunk overlap with existing doc) ---
    await _check_modified_version(tenant_id, document_id, cdc_hashes, hash_repo, db)

    # --- Store hashes ---
    await hash_repo.upsert(
        sha256=sha256,
        document_id=document_id,
        phashes=[],          # populated in Phase 2 (Docling image extraction)
        fastcdc_chunks=cdc_hashes,
    )

    await emit(tenant_id, document_id, "dedup", "done",
               f"New document — {len(cdc_hashes)} CDC chunks computed")
    return "new"


def _compute_fastcdc_hashes(data: bytes) -> list[str]:
    """Return SHA-256 hashes of FastCDC chunks."""
    chunks = list(fastcdc(data, min_size=CDC_MIN, avg_size=CDC_AVG, max_size=CDC_MAX))
    return [
        hashlib.sha256(data[c.offset: c.offset + c.length]).hexdigest()
        for c in chunks
    ]


async def _check_modified_version(
    tenant_id: str,
    document_id: str,
    new_hashes: list[str],
    hash_repo: HashStoreRepository,
    db: object,
) -> None:
    """If a previous version of this document exists (same filename, >50% CDC overlap),
    mark it as a modified upload so downstream stages process only changed chunks."""
    doc = await db.documents.find_one(  # type: ignore[union-attr]
        {"_id": __import__("bson").ObjectId(document_id), "tenant_id": tenant_id}
    )
    if doc is None:
        return
    filename: str = doc.get("filename", "")

    # Find previous document with the same filename (not the current one)
    prev = await db.documents.find_one(  # type: ignore[union-attr]
        {
            "tenant_id": tenant_id,
            "filename": filename,
            "_id": {"$ne": __import__("bson").ObjectId(document_id)},
            "status": {"$nin": ["deleted", "deduped"]},
        },
        sort=[("created_at", -1)],
    )
    if prev is None:
        return

    prev_sha256: str = prev.get("sha256", "")
    if not prev_sha256:
        return

    prev_hashes = await hash_repo.get_fastcdc_chunks(prev_sha256)
    if not prev_hashes:
        return

    overlap = len(set(new_hashes) & set(prev_hashes)) / max(len(prev_hashes), 1)
    if overlap > 0.5:
        logger.info(
            "Modified document detected",
            document_id=document_id,
            prev_doc_id=str(prev["_id"]),
            overlap=f"{overlap:.0%}",
        )
        await db.documents.update_one(  # type: ignore[union-attr]
            {"_id": __import__("bson").ObjectId(document_id)},
            {"$set": {"previous_version_id": str(prev["_id"]), "cdc_overlap": overlap}},
        )
