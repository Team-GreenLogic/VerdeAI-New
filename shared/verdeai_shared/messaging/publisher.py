"""Message publisher helpers."""

import json

import aio_pika
from pydantic import BaseModel

from verdeai_shared.messaging.connection import get_channel


async def publish(
    exchange_name: str,
    routing_key: str,
    payload: BaseModel,
) -> None:
    """Publish a Pydantic model as a JSON message to the named exchange."""
    channel = await get_channel()
    exchange = await channel.get_exchange(exchange_name)
    body = payload.model_dump_json().encode()
    message = aio_pika.Message(
        body=body,
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await exchange.publish(message, routing_key=routing_key)
    await channel.close()
