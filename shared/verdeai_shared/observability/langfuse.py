"""Langfuse client initialisation."""

from typing import Any

from verdeai_shared.settings import settings


def get_langfuse() -> Any:
    """Return an initialised Langfuse client, or None if keys are not configured."""
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return None
    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]
        return Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
    except ImportError:
        return None
