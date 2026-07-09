"""Publish ISO version build events to RabbitMQ."""

import aio_pika

from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.messaging.events import IsoVersionBuildRequested


async def publish_iso_build_requested(event: IsoVersionBuildRequested) -> None:
    channel = await get_channel()
    exchange = await channel.get_exchange("iso")
    await exchange.publish(
        aio_pika.Message(
            body=event.model_dump_json().encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key="iso.build.requested",
    )
    await channel.close()
