"""Recommendation service — Dramatiq worker bootstrap.

Full implementation in Phase 7.
"""

from verdeai_shared.logging import configure_logging
from verdeai_shared.observability.tracing import configure_tracing

from app.config import settings

configure_logging(settings.SERVICE_NAME)
configure_tracing(settings.SERVICE_NAME)

if __name__ == "__main__":
    import asyncio
    from loguru import logger
    logger.info("Recommendation service started — awaiting Phase 7 implementation")
    asyncio.get_event_loop().run_forever()
