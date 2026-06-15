"""Langfuse SDK initialisation — call init_langfuse() once at service startup."""

import os

from verdeai_shared.settings import settings


def init_langfuse() -> None:
    """Configure Langfuse SDK globals so @observe and langfuse.openai pick up credentials.

    Safe to call multiple times (idempotent). No-op if keys are not configured.
    Must be called before the first LLM call so the instrumented AsyncOpenAI
    client is created with Langfuse already active.

    Model pricing must be registered manually via the Langfuse UI:
    http://localhost:3000 → Settings → Models.
    """
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return

    # .env uses LANGFUSE_BASE_URL; the Langfuse SDK reads LANGFUSE_HOST.
    host = settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST

    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.LANGFUSE_PUBLIC_KEY)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.LANGFUSE_SECRET_KEY)
    # Always write HOST — .env has BASE_URL alias, not HOST, so setdefault won't help.
    os.environ["LANGFUSE_HOST"] = host
