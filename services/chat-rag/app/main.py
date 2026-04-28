"""Chat RAG — FastAPI service entrypoint.

Full implementation in Phase 8.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from loguru import logger

from verdeai_shared.logging import configure_logging
from verdeai_shared.observability.tracing import configure_tracing
from verdeai_shared.llm.openrouter_client import aclose as llm_aclose
from verdeai_shared.db.mongo import close_client

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings.SERVICE_NAME)
    configure_tracing(settings.SERVICE_NAME)
    logger.info("Chat RAG service starting up — Phase 8 stub")
    yield
    logger.info("Chat RAG service shutting down")
    await llm_aclose()
    await close_client()


app = FastAPI(
    title="VerdeAI Chat RAG",
    version="0.1.0",
    description="Chat RAG service — full implementation in Phase 8",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
