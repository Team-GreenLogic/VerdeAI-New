"""Stage 5 — Embedding.

Loads all chunks for this document, batch-embeds via Voyage AI,
and writes the embedding vectors back to MongoDB.
Also ensures the Atlas Vector Search index exists.
"""

import bson
from loguru import logger

from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.chunks import ChunksRepository
from verdeai_shared.retrieval.embedder import embed_documents
from verdeai_shared.settings import settings

from app.progress import emit


async def run(tenant_id: str, profile_id: str, document_id: str) -> int:
    """Embed all chunks for the document. Returns number of chunks embedded."""
    db = get_database()

    await emit(tenant_id, document_id, "embed", "running", "Embedding chunks")

    chunks_repo = ChunksRepository(db, tenant_id, profile_id)
    chunks = await chunks_repo.find_by_document(document_id)

    if not chunks:
        logger.warning("No chunks to embed", document_id=document_id)
        return 0

    texts = [c.get("text", "") for c in chunks]
    embeddings = await embed_documents(texts)

    # Bulk update — single round-trip to MongoDB instead of N separate calls
    from pymongo import UpdateOne  # type: ignore[import-untyped]
    operations = [
        UpdateOne({"_id": chunk["_id"]}, {"$set": {"embedding": emb}})
        for chunk, emb in zip(chunks, embeddings)
    ]
    if operations:
        await db.chunks.bulk_write(operations, ordered=False)

    # Ensure vector search index exists (idempotent)
    await _ensure_vector_index(db)

    logger.info(
        "Chunks embedded",
        tenant_id=tenant_id,
        document_id=document_id,
        count=len(chunks),
    )
    await emit(tenant_id, document_id, "embed", "done",
               f"{len(chunks)} chunks embedded")
    return len(chunks)


def _desired_vector_index_definition() -> dict:
    return {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": settings.EMBEDDING_DIMENSIONS,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "tenant_id"},
            {"type": "filter", "path": "profile_id"},
            {"type": "filter", "path": "document_id"},
            {"type": "filter", "path": "content_type"},
            {"type": "filter", "path": "superseded"},
            {"type": "filter", "path": "created_at"},
        ]
    }


async def _ensure_vector_index(db: object) -> None:
    """Create chunks_vector_idx if missing, or update it in place if its filter
    fields have fallen behind the desired definition (e.g. a new filter field —
    such as ``profile_id`` — was added to this function after the index already
    existed in a live deployment; merely checking the index *name* would never
    pick that up, silently leaving queries that filter on the new field broken)."""
    index_name = settings.VECTOR_INDEX_NAME
    definition = _desired_vector_index_definition()
    desired_paths = {f["path"] for f in definition["fields"]}
    try:
        existing = await db.chunks.list_search_indexes().to_list(length=None)  # type: ignore[union-attr]
        existing_by_name = {idx.get("name"): idx for idx in existing}
        current = existing_by_name.get(index_name)

        if current is None:
            await db.chunks.create_search_index(  # type: ignore[union-attr]
                {"name": index_name, "type": "vectorSearch", "definition": definition}
            )
            logger.info("Created vector search index", index=index_name)
            return

        current_paths = {
            f.get("path") for f in current.get("latestDefinition", {}).get("fields", [])
        }
        if not desired_paths.issubset(current_paths):
            # update_search_index rejects vectorSearch-type definitions on at
            # least the mongodb-atlas-local emulator ("mappings" is required,
            # a classic-Search-type requirement) — drop and recreate instead,
            # which works uniformly on both real Atlas and the local emulator.
            await db.chunks.drop_search_index(index_name)  # type: ignore[union-attr]
            await db.chunks.create_search_index(  # type: ignore[union-attr]
                {"name": index_name, "type": "vectorSearch", "definition": definition}
            )
            logger.info(
                "Recreated vector search index with new filter fields",
                index=index_name,
                added=sorted(desired_paths - current_paths),
            )
    except Exception as exc:
        # Index creation/update is async in Atlas — log but don't fail
        logger.warning("Vector index check/create/update skipped", error=str(exc))

