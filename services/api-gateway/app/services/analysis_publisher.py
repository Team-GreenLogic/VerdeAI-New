"""Publish analysis events to RabbitMQ."""

import aio_pika

from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.messaging.events import AnalysisRequested


async def publish_analysis_requested(event: AnalysisRequested) -> None:
    channel = await get_channel()
    exchange = await channel.get_exchange("analyses")
    await exchange.publish(
        aio_pika.Message(
            body=event.model_dump_json().encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key="analysis.requested",
    )
    await channel.close()
