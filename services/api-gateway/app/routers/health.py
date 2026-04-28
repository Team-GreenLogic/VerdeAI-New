"""Health and readiness endpoints."""

from fastapi import APIRouter
from loguru import logger

from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — always returns 200 if the process is alive."""
    return HealthResponse(status="ok")


@router.get("/readiness", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    """Readiness probe — checks connectivity to Mongo, RabbitMQ, and Redis."""
    checks: dict[str, str] = {}
    all_ok = True

    # MongoDB
    try:
        from verdeai_shared.db.mongo import get_client
        await get_client().admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception as exc:
        logger.warning("MongoDB readiness check failed", error=str(exc))
        checks["mongodb"] = f"error: {exc}"
        all_ok = False

    # RabbitMQ
    try:
        from verdeai_shared.messaging.connection import get_connection
        conn = await get_connection()
        if conn.is_closed:
            raise RuntimeError("connection is closed")
        checks["rabbitmq"] = "ok"
    except Exception as exc:
        logger.warning("RabbitMQ readiness check failed", error=str(exc))
        checks["rabbitmq"] = f"error: {exc}"
        all_ok = False

    # Redis
    try:
        import redis.asyncio as aioredis
        from verdeai_shared.settings import settings
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.warning("Redis readiness check failed", error=str(exc))
        checks["redis"] = f"error: {exc}"
        all_ok = False

    from fastapi import HTTPException
    if not all_ok:
        raise HTTPException(status_code=503, detail={"status": "not ready", "checks": checks})

    return ReadinessResponse(status="ok", checks=checks)
