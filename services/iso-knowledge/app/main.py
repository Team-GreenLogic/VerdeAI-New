"""ISO Knowledge service — worker bootstrap.

Full implementation in Phase 4.
"""

from verdeai_shared.logging import configure_logging
from verdeai_shared.observability.tracing import configure_tracing

from app.config import settings

configure_logging(settings.SERVICE_NAME)
configure_tracing(settings.SERVICE_NAME)

if __name__ == "__main__":
    import asyncio
    from loguru import logger
    logger.info("ISO Knowledge service started — awaiting Phase 4 implementation")
    asyncio.get_event_loop().run_forever()
