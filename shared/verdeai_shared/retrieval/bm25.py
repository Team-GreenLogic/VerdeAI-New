"""BM25 per-tenant index — backed by bm25s, serialised in MongoDB."""

import asyncio
import pickle
from typing import Any

import bm25s  # type: ignore[import-untyped]

from verdeai_shared.settings import settings


async def bm25_search(
    db: Any,  # AsyncIOMotorDatabase
    tenant_id: str,
    query: str,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Run BM25 retrieval for the given tenant. Returns list of {chunk_id, score}."""
    k = top_k or settings.RETRIEVAL_TOP_K
    record = await db["bm25_indexes"].find_one({"tenant_id": tenant_id})
    if record is None or not record.get("serialized"):
        return []

    index: bm25s.BM25 = pickle.loads(record["serialized"])  # noqa: S301
    chunk_ids: list[str] = record.get("chunk_ids", [])

    tokenized = bm25s.tokenize(query)
    results, scores = index.retrieve(tokenized, k=min(k, len(chunk_ids)))

    output: list[dict[str, Any]] = []
    for idx, score in zip(results[0].tolist(), scores[0].tolist()):
        if idx < len(chunk_ids):
            output.append({"chunk_id": chunk_ids[idx], "score": float(score)})
    return output


async def update_bm25_index(
    db: Any,  # AsyncIOMotorDatabase
    tenant_id: str,
    new_texts: list[str],
    new_chunk_ids: list[str],
) -> None:
    """Rebuild or extend the BM25 index for a tenant."""
    record = await db["bm25_indexes"].find_one({"tenant_id": tenant_id})
    existing_texts: list[str] = []
    existing_ids: list[str] = []

    if record and record.get("serialized"):
        existing_ids = record.get("chunk_ids", [])
        existing_texts = record.get("texts", [])

    all_texts = existing_texts + new_texts
    all_ids = existing_ids + new_chunk_ids

    tokenized = bm25s.tokenize(all_texts)
    index = bm25s.BM25()
    index.index(tokenized)
    serialized = pickle.dumps(index)

    await db["bm25_indexes"].update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {
                "tenant_id": tenant_id,
                "serialized": serialized,
                "chunk_ids": all_ids,
                "texts": all_texts,
                "version": (record.get("version", 0) + 1) if record else 1,
            }
        },
        upsert=True,
    )
