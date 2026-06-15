"""Base async message consumer."""

import asyncio
from collections.abc import Callable, Awaitable
from typing import Any

import aio_pika
import aiormq.exceptions
from aio_pika import IncomingMessage
from loguru import logger

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
        try:
            async with message.process(requeue=True):
                try:
                    await self._handler(message)
                except Exception:
                    # Logged by caller; requeue=True nacks so RabbitMQ retries
                    # up to the queue's x-delivery-limit.
                    raise
        except aiormq.exceptions.ChannelInvalidStateError:
            # The AMQP channel was closed (e.g. connection reset or shutdown)
            # before the nack/ack could be sent.  RabbitMQ automatically
            # requeues unacknowledged messages when the consumer disconnects,
            # so no data is lost.  Suppress to avoid crash-looping the worker.
            logger.warning(
                "AMQP channel closed during message cleanup — "
                "message will be requeued by RabbitMQ on reconnect"
            )
