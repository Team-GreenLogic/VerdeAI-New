"""Motor async MongoDB client factory."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase  # type: ignore[import-untyped]

from verdeai_shared.settings import settings

_client: AsyncIOMotorClient | None = None  # type: ignore[type-arg]


def get_client() -> AsyncIOMotorClient:  # type: ignore[type-arg]
    """Return the singleton Motor client, creating it on first call."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URI)
    return _client


def get_database() -> AsyncIOMotorDatabase:  # type: ignore[type-arg]
    """Return the configured database handle."""
    return get_client()[settings.MONGO_DB]


async def close_client() -> None:
    """Close the Motor client (call on app shutdown)."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
