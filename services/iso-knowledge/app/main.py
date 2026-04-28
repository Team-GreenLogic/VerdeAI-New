"""ISO Knowledge service — one-shot seeder."""

import asyncio

from loguru import logger

from verdeai_shared.logging import configure_logging
from verdeai_shared.observability.tracing import configure_tracing

from app.config import settings
from app.seed_iso import run_seed

configure_logging(settings.SERVICE_NAME)
configure_tracing(settings.SERVICE_NAME)


async def _main() -> None:
    await run_seed(demo_tenant_id=settings.DEMO_TENANT_ID)
    logger.info("Seeding complete — exiting")


if __name__ == "__main__":
    asyncio.run(_main())
