"""Document Processor — aio-pika consumer entrypoint."""

import asyncio

from loguru import logger

from verdeai_shared.logging import configure_logging
from verdeai_shared.messaging.consumer import AsyncConsumer
from verdeai_shared.messaging.connection import close_connection
from verdeai_shared.observability.tracing import configure_tracing

from app.config import settings
from app.actors import handle_document_deleted, handle_document_uploaded

configure_logging(settings.SERVICE_NAME)
configure_tracing(settings.SERVICE_NAME)

_QUEUE = "documents.process"
_INVALIDATE_QUEUE = "documents.invalidate"
_MAX_RETRIES = 12
_RETRY_DELAY = 5  # seconds between attempts


async def _run() -> None:
    logger.info("Document Processor starting", queue=_QUEUE)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            consumer = AsyncConsumer(queue_name=_QUEUE, handler=handle_document_uploaded)
            invalidate_consumer = AsyncConsumer(queue_name=_INVALIDATE_QUEUE, handler=handle_document_deleted)
            await consumer.start()
            await invalidate_consumer.start()
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

    logger.info("Listening for messages", queue=_QUEUE)
    # Block forever — shutdown via SIGTERM/SIGINT
    await asyncio.get_running_loop().create_future()


async def _shutdown() -> None:
    await close_connection()
    logger.info("Document Processor shut down")


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
