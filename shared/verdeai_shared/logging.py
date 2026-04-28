"""Loguru-based structured logging with OpenTelemetry hook."""

import sys
from typing import TYPE_CHECKING

from loguru import logger

from verdeai_shared.settings import settings

if TYPE_CHECKING:
    pass


def configure_logging(service_name: str | None = None) -> None:
    """Configure loguru with structured output and OTel hook."""
    name = service_name or settings.SERVICE_NAME

    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            f"<cyan>{name}</cyan> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message} | {extra}"
        ),
        serialize=settings.ENVIRONMENT != "development",
        enqueue=True,
    )


def get_logger(service: str | None = None) -> "logger.__class__":  # type: ignore[name-defined]
    """Return a logger bound with service context."""
    return logger.bind(service=service or settings.SERVICE_NAME)
