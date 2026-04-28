"""Voyage AI reranker — rerank-2.5."""

import asyncio
from typing import Any

import voyageai  # type: ignore[import-untyped]

from verdeai_shared.settings import settings

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    return _client


async def rerank(
    query: str,
    documents: list[str],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Rerank documents by relevance to the query. Returns sorted list with scores."""
    client = _get_client()
    k = top_k or settings.RERANK_TOP_K
    result = await asyncio.to_thread(
        client.rerank,
        query,
        documents,
        model=settings.VOYAGE_RERANKER_MODEL,
        top_k=k,
    )
    return [
        {"index": r.index, "score": r.relevance_score, "document": r.document}
        for r in result.results
    ]
