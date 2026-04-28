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
) -> None:
    """Publish a progress event to the glass-box channel for this job."""
    channel = f"glassbox.{tenant_id}.{job_id}"
    payload = json.dumps({"stage": stage, "status": status, "detail": detail})
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        await r.publish(channel, payload)
    finally:
        await r.aclose()
