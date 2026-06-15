"""Publish glass-box progress events to Redis pubsub."""

import json

import redis.asyncio as aioredis

from verdeai_shared.settings import settings

_HIST_TTL = 7200  # 2 hours
_MAX_TOKENS = 1000  # cap per-clause thinking token replay


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
    step: str | None = None,
    step_index: int | None = None,
    step_total: int | None = None,
    redis_client: aioredis.Redis | None = None,  # type: ignore[type-arg]
) -> None:
    """Publish a progress event to the glass-box channel for this job.

    Structural events (everything except thinking_token) are appended to a
    Redis list so reconnecting clients can replay full clause progress.

    thinking_token events are stored in a separate bounded list that is reset
    on each new clause (thinking event), keeping only the current clause's
    partial reasoning for replay.
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
    if step is not None:
        payload["step"] = step
    if step_index is not None:
        payload["step_index"] = step_index
    if step_total is not None:
        payload["step_total"] = step_total

    channel = f"glassbox.{tenant_id}.{job_id}"
    hist_key = f"glassbox_hist.{tenant_id}.{job_id}"
    tokens_key = f"glassbox_tokens.{tenant_id}.{job_id}"
    serialized = json.dumps(payload)

    own_client = redis_client is None
    r: aioredis.Redis = redis_client if redis_client is not None else aioredis.from_url(settings.REDIS_URL)  # type: ignore[type-arg]
    try:
        await r.publish(channel, serialized)

        if stage == "thinking_token":
            # Bounded per-clause token buffer — keep only the last _MAX_TOKENS
            await r.rpush(tokens_key, serialized)
            await r.ltrim(tokens_key, -_MAX_TOKENS, -1)
            await r.expire(tokens_key, _HIST_TTL)
        else:
            # Structural event — append to main history list
            await r.rpush(hist_key, serialized)
            await r.expire(hist_key, _HIST_TTL)
            if stage == "thinking":
                # New clause starting — discard previous clause's token buffer
                await r.delete(tokens_key)
    finally:
        if own_client:
            await r.aclose()
