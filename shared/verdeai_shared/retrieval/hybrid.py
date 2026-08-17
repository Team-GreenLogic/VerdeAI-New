"""Hybrid retrieval: vector + BM25 + RRF fusion + Voyage rerank."""

from typing import Any

from verdeai_shared.retrieval.reranker import rerank
from verdeai_shared.retrieval.vector_search import vector_search_chunks
from verdeai_shared.retrieval.bm25 import bm25_search
from verdeai_shared.settings import settings


def _rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score."""
    return 1.0 / (k + rank)


async def hybrid_retrieve(
    db: Any,
    tenant_id: str,
    query: str,
    query_vector: list[float],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Run vector + BM25 retrieval and fuse with RRF, then rerank.

    Returns up to RERANK_TOP_K chunks sorted by rerank score.
    """
    k = top_k or settings.RETRIEVAL_TOP_K

    # Parallel retrieval
    vector_results, bm25_results = await _run_both(
        db, tenant_id, query, query_vector, k
    )

    # Build RRF score map: {chunk_id: rrf_score}
    scores: dict[str, float] = {}

    for rank, chunk in enumerate(vector_results):
        cid = str(chunk["_id"])
        scores[cid] = scores.get(cid, 0.0) + _rrf_score(rank)

    # Fetch chunk ids from bm25 hits and merge
    bm25_id_set: set[str] = set()
    for rank, hit in enumerate(bm25_results):
        cid = hit["chunk_id"]
        bm25_id_set.add(cid)
        scores[cid] = scores.get(cid, 0.0) + _rrf_score(rank)

    # Merge: collect all unique chunks from vector results
    chunk_map: dict[str, dict[str, Any]] = {
        str(c["_id"]): c for c in vector_results
    }

    # Fetch BM25-only chunks from DB
    missing_ids = bm25_id_set - set(chunk_map.keys())
    if missing_ids:
        from bson import ObjectId
        cursor = db["chunks"].find({"_id": {"$in": [ObjectId(i) for i in missing_ids]}})
        for doc in await cursor.to_list(length=None):
            chunk_map[str(doc["_id"])] = doc

    # Sort by RRF score
    fused = sorted(chunk_map.values(), key=lambda c: scores.get(str(c["_id"]), 0.0), reverse=True)
    fused = fused[:k]

    # Rerank
    texts = [
        f"{c.get('context_preamble', '')}\n\n{c.get('text', '')}".strip()
        for c in fused
    ]
    if not texts:
        return []

    reranked = await rerank(query, texts, top_k=settings.RERANK_TOP_K)
    # Surface the rerank relevance score onto each chunk (previously discarded) so
    # downstream evidence-grading can drop marginal/irrelevant chunks instead of
    # always handing the LLM a fixed top-N regardless of quality.
    return [{**fused[r["index"]], "rerank_score": r["score"]} for r in reranked]


async def _run_both(
    db: Any,
    tenant_id: str,
    query: str,
    query_vector: list[float],
    k: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run vector and BM25 retrieval concurrently."""
    import asyncio
    vector_task = asyncio.create_task(vector_search_chunks(db, tenant_id, query_vector, k))
    bm25_task = asyncio.create_task(bm25_search(db, tenant_id, query, k))
    vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task)
    return vector_results, bm25_results
