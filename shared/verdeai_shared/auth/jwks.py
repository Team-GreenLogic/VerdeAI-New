"""JWKS fetcher with TTL cache and kid-miss refresh."""

import asyncio
import time
from typing import Any

import httpx

from verdeai_shared.settings import settings

# Cache structure: {kid: {"key": <public-key-bytes>, "fetched_at": float}}
_cache: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()


async def _fetch_jwks() -> dict[str, Any]:
    """Fetch JWKS from Keycloak and return raw JSON."""
    url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


async def _populate_cache() -> None:
    """Re-fetch JWKS and populate the in-memory cache."""
    data = await _fetch_jwks()
    now = time.time()
    for jwk in data.get("keys", []):
        kid: str = jwk["kid"]
        _cache[kid] = {"key": jwk, "fetched_at": now}


def _is_expired(entry: dict[str, Any]) -> bool:
    return (time.time() - entry["fetched_at"]) > settings.KEYCLOAK_JWKS_CACHE_TTL_SECONDS


async def get_public_key(kid: str, *, allow_refresh: bool = True) -> dict[str, Any]:
    """Return the JWK dict for the given kid.

    Fetches from Keycloak on cache miss or TTL expiry.
    Refreshes once on kid-miss if ``allow_refresh=True``.
    """
    async with _lock:
        entry = _cache.get(kid)
        if entry is None or _is_expired(entry):
            await _populate_cache()
            entry = _cache.get(kid)

    if entry is None:
        if allow_refresh:
            # One-shot refresh: force re-fetch even if we just populated
            async with _lock:
                await _populate_cache()
                entry = _cache.get(kid)

    if entry is None:
        raise KeyError(f"Unknown kid: {kid!r}")

    return entry["key"]  # type: ignore[return-value]
