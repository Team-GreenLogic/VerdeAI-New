"""BM25 per-(tenant, org profile) index — backed by bm25s, serialised in MongoDB."""

import asyncio
import pickle
from typing import Any

import bm25s  # type: ignore[import-untyped]

from verdeai_shared.settings import settings


async def bm25_search(
    db: Any,  # AsyncIOMotorDatabase
    tenant_id: str,
    profile_id: str,
    query: str,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Run BM25 retrieval for the given tenant + org profile. Returns list of {chunk_id, score}."""
    k = top_k or settings.RETRIEVAL_TOP_K
    record = await db["bm25_indexes"].find_one({"tenant_id": tenant_id, "profile_id": profile_id})
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


async def remove_document_from_bm25_index(
    db: Any,  # AsyncIOMotorDatabase
    tenant_id: str,
    profile_id: str,
    chunk_ids_to_remove: list[str],
) -> None:
    """Remove specific chunk IDs from the (tenant, profile) BM25 index and rebuild."""
    key = {"tenant_id": tenant_id, "profile_id": profile_id}
    record = await db["bm25_indexes"].find_one(key)
    if not record or not record.get("serialized"):
        return

    remove_set = set(chunk_ids_to_remove)
    existing_ids: list[str] = record.get("chunk_ids", [])
    existing_texts: list[str] = record.get("texts", [])

    kept = [
        (cid, txt)
        for cid, txt in zip(existing_ids, existing_texts)
        if cid not in remove_set
    ]

    if not kept:
        await db["bm25_indexes"].delete_one(key)
        return

    new_ids, new_texts = zip(*kept)
    serialized = await asyncio.to_thread(_build_and_serialize_index, list(new_texts))

    await db["bm25_indexes"].update_one(
        key,
        {
            "$set": {
                "serialized": serialized,
                "chunk_ids": list(new_ids),
                "texts": list(new_texts),
                "version": record.get("version", 0) + 1,
            }
        },
    )


async def update_bm25_index(
    db: Any,  # AsyncIOMotorDatabase
    tenant_id: str,
    profile_id: str,
    new_texts: list[str],
    new_chunk_ids: list[str],
) -> None:
    """Rebuild or extend the BM25 index for a (tenant, org profile) pair."""
    key = {"tenant_id": tenant_id, "profile_id": profile_id}
    record = await db["bm25_indexes"].find_one(key)
    existing_texts: list[str] = []
    existing_ids: list[str] = []

    if record and record.get("serialized"):
        existing_ids = record.get("chunk_ids", [])
        existing_texts = record.get("texts", [])

    all_texts = existing_texts + new_texts
    all_ids = existing_ids + new_chunk_ids

    serialized = await asyncio.to_thread(_build_and_serialize_index, all_texts)

    await db["bm25_indexes"].update_one(
        key,
        {
            "$set": {
                "tenant_id": tenant_id,
                "profile_id": profile_id,
                "serialized": serialized,
                "chunk_ids": all_ids,
                "texts": all_texts,
                "version": (record.get("version", 0) + 1) if record else 1,
            }
        },
        upsert=True,
    )


def _build_and_serialize_index(texts: list[str]) -> bytes:
    """Helper to tokenize and build BM25 index synchronously."""
    tokenized = bm25s.tokenize(texts)
    index = bm25s.BM25()
    index.index(tokenized)
    return pickle.dumps(index)

