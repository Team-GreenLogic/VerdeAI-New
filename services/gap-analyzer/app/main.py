"""Gap Analyzer — Dramatiq + LangGraph worker bootstrap.

Full implementation in Phases 5–6.
"""

from verdeai_shared.logging import configure_logging
from verdeai_shared.observability.tracing import configure_tracing

from app.config import settings

configure_logging(settings.SERVICE_NAME)
configure_tracing(settings.SERVICE_NAME)

if __name__ == "__main__":
    import asyncio
    from loguru import logger
    logger.info("Gap Analyzer service started — awaiting Phase 5 implementation")
    asyncio.get_event_loop().run_forever()
