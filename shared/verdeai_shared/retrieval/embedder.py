"""Voyage AI embedder — voyage-3-large (1024 dims)."""

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


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a list of document texts. Batches up to EMBED_BATCH_SIZE."""
    all_embeddings: list[list[float]] = []
    batch_size = settings.EMBED_BATCH_SIZE

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        all_embeddings.extend(await _embed_batch(batch, input_type="document"))

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """Embed a single query string. Retries up to _MAX_ATTEMPTS times."""
    result = await _embed_batch([text], input_type="query")
    return result[0]


async def _embed_batch(texts: list[str], *, input_type: str) -> list[list[float]]:
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            client = _get_client()
            result = await asyncio.to_thread(
                client.embed,
                texts,
                model=settings.VOYAGE_EMBEDDING_MODEL,
                input_type=input_type,
            )
            return result.embeddings  # type: ignore[no-any-return]
        except Exception as exc:
            last_exc = exc
            _reset_client()
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "Voyage embed failed, retrying",
                    attempt=attempt + 1,
                    max_attempts=_MAX_ATTEMPTS,
                    delay=round(delay, 2),
                    error=str(exc),
                )
                await asyncio.sleep(delay)

    raise RuntimeError(f"Voyage embed failed after {_MAX_ATTEMPTS} attempts") from last_exc
