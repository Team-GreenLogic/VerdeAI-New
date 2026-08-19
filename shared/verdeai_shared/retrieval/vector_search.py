"""MongoDB Atlas Vector Search aggregation helper."""

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]

from verdeai_shared.settings import settings


async def vector_search_chunks(
    db: AsyncIOMotorDatabase,  # type: ignore[type-arg]
    tenant_id: str,
    query_vector: list[float],
    top_k: int | None = None,
    document_id: str | None = None,
    created_after: datetime | None = None,
    profile_id: str | None = None,
) -> list[dict[str, Any]]:
    """Run $vectorSearch on the chunks collection filtered by tenant_id (and profile_id,
    when given, to keep a gap-analysis/chat run's evidence isolated to one org profile).

    Superseded chunks (older versions of a re-uploaded document) are always
    excluded. When ``created_after`` is given, only chunks ingested after that
    instant are returned — used by delta re-analysis to look at new evidence only.
    """
    k = top_k or settings.RETRIEVAL_TOP_K
    pre_filter: dict[str, Any] = {
        "tenant_id": {"$eq": tenant_id},
        "superseded": {"$eq": False},
    }
    if profile_id:
        pre_filter["profile_id"] = {"$eq": profile_id}
    if document_id:
        pre_filter["document_id"] = {"$eq": document_id}
    if created_after is not None:
        pre_filter["created_at"] = {"$gt": created_after}

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
                "profile_id": 1,
                "document_id": 1,
                "page": 1,
                "text": 1,
                "context_preamble": 1,
                "content_type": 1,
                "created_at": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = db["chunks"].aggregate(pipeline)
    return await cursor.to_list(length=None)
