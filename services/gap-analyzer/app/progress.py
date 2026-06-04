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
) -> None:
    """Publish a progress event to the glass-box channel for this job."""
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
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        await r.publish(channel, json.dumps(payload))
    finally:
        await r.aclose()
