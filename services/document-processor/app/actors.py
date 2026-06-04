"""Document processing pipeline — aio-pika message handler."""

import json

import aio_pika
from aio_pika import IncomingMessage
from loguru import logger

from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.db.repositories.hash_store import HashStoreRepository
from verdeai_shared.messaging.events import DocumentDeleted, DocumentReady, DocumentUploaded
from verdeai_shared.retrieval.bm25 import remove_document_from_bm25_index

from app.pipeline import (
    stage1_dedup,
    stage2_parse,
    stage3_chunk,
    stage4_image,
    stage5_embed,
    stage6_index,
)
from app.progress import emit


async def handle_document_uploaded(message: IncomingMessage) -> None:
    """Deserialise a DocumentUploaded event and run the full processing pipeline."""
    raw = message.body.decode()
    try:
        event = DocumentUploaded.model_validate_json(raw)
    except Exception as exc:
        logger.error("Failed to parse DocumentUploaded event", error=str(exc), raw=raw)
        raise

    tenant_id = event.tenant_id
    document_id = event.document_id

    logger.info(
        "Processing document",
        tenant_id=tenant_id,
        document_id=document_id,
        filename=event.filename,
    )

    try:
        # Stage 1 — dedup gate
        result = await stage1_dedup.run(
            tenant_id=tenant_id,
            document_id=document_id,
            sha256=event.sha256,
        )
        logger.info("Stage 1 complete", tenant_id=tenant_id, document_id=document_id, result=result)
        if result == "deduped":
            return

        # Stage 2 — LlamaParse
        pages = await stage2_parse.run(tenant_id=tenant_id, document_id=document_id)
        logger.info("Stage 2 complete", tenant_id=tenant_id, document_id=document_id, pages=pages)

        # Stage 3 — chunking + contextualisation
        chunk_count = await stage3_chunk.run(tenant_id=tenant_id, document_id=document_id)
        logger.info("Stage 3 complete", tenant_id=tenant_id, document_id=document_id, chunks=chunk_count)

        # Stage 4 — image summaries (skipped if no images)
        img_count = await stage4_image.run(tenant_id=tenant_id, document_id=document_id)
        logger.info("Stage 4 complete", tenant_id=tenant_id, document_id=document_id, images=img_count)

        # Stage 5 — embedding
        embedded = await stage5_embed.run(tenant_id=tenant_id, document_id=document_id)
        logger.info("Stage 5 complete", tenant_id=tenant_id, document_id=document_id, embedded=embedded)

        # Stage 6 — BM25 indexing
        await stage6_index.run(tenant_id=tenant_id, document_id=document_id)
        logger.info("Stage 6 complete", tenant_id=tenant_id, document_id=document_id)

        # Mark document ready
        from verdeai_shared.db.mongo import get_database
        import bson
        db = get_database()
        await db.documents.update_one(
            {"_id": bson.ObjectId(document_id)},
            {"$set": {"status": "ready"}},
        )

        # Publish DocumentReady event
        await _publish_ready(DocumentReady(
            tenant_id=tenant_id,
            document_id=document_id,
            chunks_indexed=chunk_count + img_count,
        ))

        await emit(tenant_id, document_id, "complete", "done",
                   f"Document ready — {chunk_count + img_count} chunks indexed")

    except Exception as exc:
        logger.error(
            "Pipeline failed",
            tenant_id=tenant_id,
            document_id=document_id,
            error=str(exc),
        )
        from verdeai_shared.db.mongo import get_database
        import bson
        try:
            db = get_database()
            await db.documents.update_one(
                {"_id": bson.ObjectId(document_id)},
                {"$set": {"status": "failed", "error": str(exc)}},
            )
        except Exception:
            pass
        await emit(tenant_id, document_id, "complete", "failed", str(exc))
        raise


async def handle_document_deleted(message: IncomingMessage) -> None:
    """Consume DocumentDeleted: hard-delete chunks and prune BM25 index."""
    raw = message.body.decode()
    try:
        event = DocumentDeleted.model_validate_json(raw)
    except Exception as exc:
        logger.error("Failed to parse DocumentDeleted event", error=str(exc), raw=raw)
        raise

    tenant_id = event.tenant_id
    document_id = event.document_id

    logger.info("Invalidating document chunks", tenant_id=tenant_id, document_id=document_id)

    from verdeai_shared.db.mongo import get_database
    db = get_database()

    # Collect chunk IDs before deletion (needed to prune BM25)
    cursor = db["chunks"].find(
        {"document_id": document_id, "tenant_id": tenant_id},
        {"_id": 1},
    )
    chunk_docs = await cursor.to_list(length=None)
    chunk_ids = [str(c["_id"]) for c in chunk_docs]

    # Prune BM25 index first (uses chunk IDs still present in DB)
    if chunk_ids:
        await remove_document_from_bm25_index(db, tenant_id, chunk_ids)
        logger.info("BM25 index pruned", tenant_id=tenant_id, removed=len(chunk_ids))

    # Hard-delete chunks (vector search auto-excludes once docs are gone)
    result = await db["chunks"].delete_many(
        {"document_id": document_id, "tenant_id": tenant_id}
    )
    logger.info(
        "Chunks deleted",
        tenant_id=tenant_id,
        document_id=document_id,
        count=result.deleted_count,
    )

    # Remove hash_store entry so the same file can be re-uploaded cleanly
    hash_repo = HashStoreRepository(db, tenant_id)
    await hash_repo.delete_by_document(document_id)
    logger.info("Hash store entry deleted", tenant_id=tenant_id, document_id=document_id)


async def _publish_ready(event: DocumentReady) -> None:
    """Publish DocumentReady to the documents exchange."""
    try:
        channel = await get_channel()
        exchange = await channel.get_exchange("documents")
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="document.ready",
        )
        await channel.close()
    except Exception as exc:
        logger.warning("Failed to publish DocumentReady", error=str(exc))
