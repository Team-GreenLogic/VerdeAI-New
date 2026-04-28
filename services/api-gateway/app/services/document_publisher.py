"""Publish document events to RabbitMQ."""

import aio_pika

from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.messaging.events import DocumentUploaded, DocumentDeleted


async def publish_document_uploaded(event: DocumentUploaded) -> None:
    channel = await get_channel()
    exchange = await channel.get_exchange("documents")
    body = event.model_dump_json().encode()
    await exchange.publish(
        aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key="document.uploaded",
    )
    await channel.close()


async def publish_document_deleted(event: DocumentDeleted) -> None:
    channel = await get_channel()
    exchange = await channel.get_exchange("documents")
    body = event.model_dump_json().encode()
    await exchange.publish(
        aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key="document.deleted",
    )
    await channel.close()
