"""Recommendation service — aio-pika consumer entrypoint."""

import asyncio

from loguru import logger
from verdeai_shared.llm.openrouter_client import aclose as llm_aclose
from verdeai_shared.logging import configure_logging
from verdeai_shared.messaging.connection import close_connection
from verdeai_shared.messaging.consumer import AsyncConsumer
from verdeai_shared.observability.langfuse import init_langfuse
from verdeai_shared.observability.tracing import configure_tracing

from app.actors import (
    handle_analysis_gaps_ready,
    handle_personalized_recommendation_requested,
)
from app.config import settings

configure_logging(settings.SERVICE_NAME)
configure_tracing(settings.SERVICE_NAME)
init_langfuse()

_QUEUES = (
    ("analyses.recommend", handle_analysis_gaps_ready),
    ("recommendations.personalize", handle_personalized_recommendation_requested),
)
_MAX_RETRIES = 12
_RETRY_DELAY = 5


async def _run() -> None:
    logger.info("Recommendation service starting", queues=[name for name, _ in _QUEUES])

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            for queue_name, handler in _QUEUES:
                consumer = AsyncConsumer(queue_name=queue_name, handler=handler)
                await consumer.start()
            break
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                logger.error("Giving up connecting to RabbitMQ", attempts=_MAX_RETRIES)
                raise
            logger.warning(
                "RabbitMQ not ready, retrying",
                attempt=attempt,
                max=_MAX_RETRIES,
                retry_in=_RETRY_DELAY,
                error=str(exc),
            )
            await asyncio.sleep(_RETRY_DELAY)

    logger.info("Listening for recommendation jobs", queues=[name for name, _ in _QUEUES])
    await asyncio.get_running_loop().create_future()


async def _shutdown() -> None:
    await llm_aclose()
    await close_connection()
    logger.info("Recommendation service shut down")


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.run_until_complete(_shutdown())
        loop.close()


if __name__ == "__main__":
    main()
