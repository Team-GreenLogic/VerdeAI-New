"""Voyage AI embedder — voyage-3-large (1024 dims)."""

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


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a list of document texts. Batches up to EMBED_BATCH_SIZE."""
    client = _get_client()
    all_embeddings: list[list[float]] = []
    batch_size = settings.EMBED_BATCH_SIZE

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        result = await asyncio.to_thread(
            client.embed,
            batch,
            model=settings.VOYAGE_EMBEDDING_MODEL,
            input_type="document",
        )
        all_embeddings.extend(result.embeddings)

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    client = _get_client()
    result = await asyncio.to_thread(
        client.embed,
        [text],
        model=settings.VOYAGE_EMBEDDING_MODEL,
        input_type="query",
    )
    return result.embeddings[0]  # type: ignore[no-any-return]
