"""Publish glass-box progress events to Redis pubsub."""

import json

import redis.asyncio as aioredis

from verdeai_shared.settings import settings


async def emit(
    tenant_id: str,
    job_id: str,
    stage: str,
    status: str,
    detail: str = "",
    *,
    completed: int | None = None,
    total: int | None = None,
    clause_id: str | None = None,
    decision: str | None = None,
    gap_count: int | None = None,
    redis_client: aioredis.Redis | None = None,  # type: ignore[type-arg]
) -> None:
    """Publish a progress event to the glass-box channel for this job.

    Pass redis_client to reuse an existing connection (e.g. for high-frequency
    per-token thinking events). If omitted a new connection is created and closed.
    """
    payload: dict = {"stage": stage, "status": status, "detail": detail}
    if completed is not None:
        payload["completed"] = completed
    if total is not None:
        payload["total"] = total
    if clause_id is not None:
        payload["clause_id"] = clause_id
    if decision is not None:
        payload["decision"] = decision
    if gap_count is not None:
        payload["gap_count"] = gap_count
    channel = f"glassbox.{tenant_id}.{job_id}"
    own_client = redis_client is None
    r: aioredis.Redis = redis_client if redis_client is not None else aioredis.from_url(settings.REDIS_URL)  # type: ignore[type-arg]
    try:
        await r.publish(channel, json.dumps(payload))
    finally:
        if own_client:
            await r.aclose()
