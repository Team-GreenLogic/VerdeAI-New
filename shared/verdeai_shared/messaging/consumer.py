"""Base async message consumer."""

import asyncio
from collections.abc import Callable, Awaitable
from typing import Any

import aio_pika
from aio_pika import IncomingMessage

from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.messaging.exchanges import declare_topology


class AsyncConsumer:
    """Wraps aio-pika queue consumption with auto-ack and error handling."""

    def __init__(
        self,
        queue_name: str,
        handler: Callable[[IncomingMessage], Awaitable[None]],
    ) -> None:
        self._queue_name = queue_name
        self._handler = handler

    async def start(self) -> None:
        channel = await get_channel()
        await channel.set_qos(prefetch_count=1)
        await declare_topology(channel)
        queue = await channel.get_queue(self._queue_name)
        await queue.consume(self._process)

    async def _process(self, message: IncomingMessage) -> None:
        async with message.process(requeue=True):
            try:
                await self._handler(message)
            except Exception:
                # Logged by caller; requeue=True handles retry up to x-delivery-limit
                raise
