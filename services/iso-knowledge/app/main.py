"""ISO Knowledge service — long-running worker + one-shot seeder."""

import asyncio

from loguru import logger

from verdeai_shared.logging import configure_logging
from verdeai_shared.messaging.connection import close_connection
from verdeai_shared.messaging.consumer import AsyncConsumer
from verdeai_shared.observability.tracing import configure_tracing

from app.actors import handle_iso_build_requested
from app.config import settings
from app.seed_iso import run_seed

configure_logging(settings.SERVICE_NAME)
configure_tracing(settings.SERVICE_NAME)

_QUEUE = "iso.build"
_MAX_RETRIES = 12
_RETRY_DELAY = 5


async def _run_worker() -> None:
    """Start the RabbitMQ consumer for ISO version build jobs."""
    logger.info("ISO Knowledge worker starting", queue=_QUEUE)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            consumer = AsyncConsumer(queue_name=_QUEUE, handler=handle_iso_build_requested)
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

    logger.info("Listening for ISO build requests", queue=_QUEUE)
    await asyncio.get_running_loop().create_future()


async def _shutdown() -> None:
    await close_connection()
    logger.info("ISO Knowledge worker shut down")


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_worker())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.run_until_complete(_shutdown())
        loop.close()


async def _seed_main() -> None:
    """One-shot seeder entry point (used by make seed-iso / CLI)."""
    await run_seed(demo_tenant_id=settings.DEMO_TENANT_ID)
    logger.info("Seeding complete — exiting")


if __name__ == "__main__":
    main()
