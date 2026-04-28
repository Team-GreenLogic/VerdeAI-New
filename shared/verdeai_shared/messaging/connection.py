"""aio-pika connection manager."""

import aio_pika
from aio_pika import Connection, Channel

from verdeai_shared.settings import settings

_connection: Connection | None = None


async def get_connection() -> Connection:
    """Return a live RabbitMQ connection, creating it lazily."""
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    return _connection


async def get_channel() -> Channel:
    """Return a new channel from the shared connection."""
    conn = await get_connection()
    return await conn.channel()


async def close_connection() -> None:
    """Close the shared connection (call on shutdown)."""
    global _connection
    if _connection is not None and not _connection.is_closed:
        await _connection.close()
    _connection = None
