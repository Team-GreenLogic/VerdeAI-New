"""Chat session history stored in Redis (sliding window)."""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from verdeai_shared.settings import settings

_TTL = 86400  # 24 hours


def _key(tenant_id: str, session_id: str) -> str:
    return f"chat_history:{tenant_id}:{session_id}"


async def load_history(
    tenant_id: str,
    session_id: str,
    window: int,
) -> list[dict[str, str]]:
    """Return the last `window` turns from Redis."""
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        raw = await r.get(_key(tenant_id, session_id))
    finally:
        await r.aclose()

    if not raw:
        return []
    try:
        turns: list[dict[str, str]] = json.loads(raw)
        return turns[-window * 2:]  # each turn = 2 messages (user + assistant)
    except Exception:
        return []


async def append_turn(
    tenant_id: str,
    session_id: str,
    question: str,
    answer: str,
    window: int,
) -> None:
    """Append a user/assistant turn to history and refresh TTL."""
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        raw = await r.get(_key(tenant_id, session_id))
        turns: list[dict[str, str]] = json.loads(raw) if raw else []
        turns.append({"role": "user", "content": question})
        turns.append({"role": "assistant", "content": answer})
        # Keep only the last window * 2 messages
        turns = turns[-(window * 2):]
        await r.setex(_key(tenant_id, session_id), _TTL, json.dumps(turns))
    finally:
        await r.aclose()
