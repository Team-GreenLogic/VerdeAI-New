"""Voyage AI reranker — rerank-2.5."""

import asyncio
import random
from typing import Any

import voyageai  # type: ignore[import-untyped]
from loguru import logger

from verdeai_shared.settings import settings

_client: Any = None

_MAX_ATTEMPTS = 3
_BASE_DELAY = 1.0  # seconds


def _get_client() -> Any:
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    return _client


def _reset_client() -> None:
    global _client
    _client = None


async def rerank(
    query: str,
    documents: list[str],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Rerank documents by relevance to the query. Returns sorted list with scores.
    Retries up to _MAX_ATTEMPTS times on transient errors.
    """
    k = top_k or settings.RERANK_TOP_K
    last_exc: Exception | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            client = _get_client()
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
        except Exception as exc:
            last_exc = exc
            _reset_client()
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "Voyage rerank failed, retrying",
                    attempt=attempt + 1,
                    max_attempts=_MAX_ATTEMPTS,
                    delay=round(delay, 2),
                    error=str(exc),
                )
                await asyncio.sleep(delay)

    raise RuntimeError(f"Voyage rerank failed after {_MAX_ATTEMPTS} attempts") from last_exc
