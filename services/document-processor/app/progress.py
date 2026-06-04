"""Publish glass-box progress events to Redis pubsub."""

import json

import redis.asyncio as aioredis

from verdeai_shared.settings import settings


_HIST_TTL = 7200  # 2 hours


async def emit(
    tenant_id: str,
    job_id: str,
    stage: str,
    status: str,
    detail: str = "",
) -> None:
    """Publish a progress event to the glass-box channel for this job.

    Also appends to a Redis list so late-connecting clients (e.g. after a
    page reload) can replay the full event history via the WS endpoint.
    """
    channel = f"glassbox.{tenant_id}.{job_id}"
    hist_key = f"glassbox_hist.{tenant_id}.{job_id}"
    payload = json.dumps({"stage": stage, "status": status, "detail": detail})
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        await r.publish(channel, payload)
        await r.rpush(hist_key, payload)
        await r.expire(hist_key, _HIST_TTL)
    finally:
        await r.aclose()
