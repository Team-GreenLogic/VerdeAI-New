"""Publish personalized recommendation research requests."""

import aio_pika
from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.messaging.events import PersonalizedRecommendationRequested


async def publish_personalized_recommendation_requested(
    event: PersonalizedRecommendationRequested,
) -> None:
    channel = await get_channel()
    try:
        exchange = await channel.get_exchange("analyses")
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="recommendation.personalized.requested",
        )
    finally:
        await channel.close()
