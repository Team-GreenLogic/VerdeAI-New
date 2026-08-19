"""Stage 6 — BM25 index update.

Loads chunk texts for this document and merges them into the per-tenant BM25 index.
"""

from loguru import logger

from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.chunks import ChunksRepository
from verdeai_shared.retrieval.bm25 import update_bm25_index

from app.progress import emit


async def run(tenant_id: str, profile_id: str, document_id: str) -> None:
    """Update the BM25 index with this document's chunks."""
    db = get_database()

    await emit(tenant_id, document_id, "index", "running", "Updating BM25 index")

    chunks_repo = ChunksRepository(db, tenant_id, profile_id)
    chunks = await chunks_repo.find_by_document(document_id)

    if not chunks:
        logger.warning("No chunks for BM25 index", document_id=document_id)
        return

    texts = [c.get("text", "") for c in chunks]
    chunk_ids = [str(c["_id"]) for c in chunks]

    await update_bm25_index(db, tenant_id, profile_id, texts, chunk_ids)

    logger.info(
        "BM25 index updated",
        tenant_id=tenant_id,
        document_id=document_id,
        chunks=len(chunks),
    )
    await emit(tenant_id, document_id, "index", "done", "BM25 index updated")
