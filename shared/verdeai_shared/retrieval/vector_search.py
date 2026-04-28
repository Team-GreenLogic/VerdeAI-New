"""MongoDB Atlas Vector Search aggregation helper."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]

from verdeai_shared.settings import settings


async def vector_search_chunks(
    db: AsyncIOMotorDatabase,  # type: ignore[type-arg]
    tenant_id: str,
    query_vector: list[float],
    top_k: int | None = None,
    document_id: str | None = None,
) -> list[dict[str, Any]]:
    """Run $vectorSearch on the chunks collection filtered by tenant_id."""
    k = top_k or settings.RETRIEVAL_TOP_K
    pre_filter: dict[str, Any] = {"tenant_id": {"$eq": tenant_id}}
    if document_id:
        pre_filter["document_id"] = {"$eq": document_id}

    pipeline: list[dict[str, Any]] = [
        {
            "$vectorSearch": {
                "index": settings.VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": k * 10,
                "limit": k,
                "filter": pre_filter,
            }
        },
        {
            "$project": {
                "_id": 1,
                "tenant_id": 1,
                "document_id": 1,
                "page": 1,
                "text": 1,
                "context_preamble": 1,
                "content_type": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = db["chunks"].aggregate(pipeline)
    return await cursor.to_list(length=None)
