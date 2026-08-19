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


async def _ensure_vector_index(db: object) -> None:
    """Create chunks_vector_idx if it doesn't already exist."""
    index_name = settings.VECTOR_INDEX_NAME
    try:
        existing = await db.chunks.list_search_indexes().to_list(length=None)  # type: ignore[union-attr]
        names = [idx.get("name") for idx in existing]
        if index_name in names:
            return

        await db.chunks.create_search_index(  # type: ignore[union-attr]
            {
                "name": index_name,
                "type": "vectorSearch",
                "definition": {
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
                },
            }
        )
        logger.info("Created vector search index", index=index_name)
    except Exception as exc:
        # Index creation is async in Atlas — log but don't fail
        logger.warning("Vector index check/create skipped", error=str(exc))
