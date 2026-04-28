"""API Gateway — FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from loguru import logger

from verdeai_shared.db.indexes import ensure_indexes
from verdeai_shared.db.mongo import close_client, get_database
from verdeai_shared.llm.openrouter_client import aclose as llm_aclose
from verdeai_shared.logging import configure_logging
from verdeai_shared.messaging.connection import close_connection
from verdeai_shared.observability.tracing import configure_tracing

from app.config import settings
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.tenant_scope import TenantScopeMiddleware
from app.routers import analyses, auth, documents, health, ws


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown."""
    configure_logging(settings.SERVICE_NAME)
    configure_tracing(settings.SERVICE_NAME)
    logger.info("API Gateway starting up")

    # Ensure MongoDB indexes exist
    try:
        db = get_database()
        await ensure_indexes(db)
        logger.info("MongoDB indexes ensured")
    except Exception as exc:
        logger.error("Failed to ensure MongoDB indexes", error=str(exc))

    yield

    logger.info("API Gateway shutting down")
    await llm_aclose()
    await close_connection()
    await close_client()


app = FastAPI(
    title="VerdeAI API Gateway",
    version="0.1.0",
    description="AI-Powered ISO 14001 Compliance Assistant — API Gateway",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware (applied in reverse order — last added = outermost)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(TenantScopeMiddleware)
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(analyses.router)
app.include_router(ws.router)
