"""Publish replayable glass-box job progress events to Redis."""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from verdeai_shared.settings import settings

_HIST_TTL = 7200
_MAX_TOKENS = 1000


async def emit(
    tenant_id: str,
    job_id: str,
    stage: str,
    status: str,
    detail: str = "",
    *,
    redis_client: Any | None = None,
    **fields: Any,
) -> None:
    """Publish and retain a structural progress event for reconnecting clients."""
    payload = {"stage": stage, "status": status, "detail": detail}
    payload.update({key: value for key, value in fields.items() if value is not None})

    channel = f"glassbox.{tenant_id}.{job_id}"
    hist_key = f"glassbox_hist.{tenant_id}.{job_id}"
    tokens_key = f"glassbox_tokens.{tenant_id}.{job_id}"
    serialized = json.dumps(payload, default=str)

    own_client = redis_client is None
    client: Any = (
        redis_client
        if redis_client is not None
        else aioredis.from_url(settings.REDIS_URL)  # type: ignore[no-untyped-call]
    )
    try:
        await client.publish(channel, serialized)
        if stage == "thinking_token":
            await client.rpush(tokens_key, serialized)
            await client.ltrim(tokens_key, -_MAX_TOKENS, -1)
            await client.expire(tokens_key, _HIST_TTL)
        else:
            await client.rpush(hist_key, serialized)
            await client.expire(hist_key, _HIST_TTL)
            if stage == "thinking":
                await client.delete(tokens_key)
    finally:
        if own_client:
            await client.aclose()
