"""Structured, schema-validated LLM completions with bounded repair retries.

Wraps ``stream_with_reasoning``/``complete`` so callers get back a validated
Pydantic model instead of a raw string. On malformed JSON or a schema-validation
failure, the model is given its own bad output plus the validation errors and
asked to correct it — up to ``settings.LLM_MAX_RETRIES`` attempts (previously
declared in settings but never actually used by any call site).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError

from verdeai_shared.llm.openrouter_client import complete, stream_with_reasoning
from verdeai_shared.settings import settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class StructuredOutputError(Exception):
    """Raised when the LLM fails to produce schema-valid JSON after all retries."""

    def __init__(self, message: str, last_raw: str = "") -> None:
        super().__init__(message)
        self.last_raw = last_raw


def _repair_message(bad_output: str, error: str, schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "role": "user",
        "content": (
            "Your previous response was not valid JSON matching the required schema.\n\n"
            f"Your previous response:\n{bad_output}\n\n"
            f"Validation error:\n{error}\n\n"
            f"Required JSON schema:\n{json.dumps(schema.model_json_schema(), indent=2)}\n\n"
            "Return ONLY the corrected JSON object. No prose, no markdown fences."
        ),
    }


_TRANSPORT_ATTEMPTS = 3
_TRANSPORT_BACKOFF_SECONDS = 2.0


def _is_transport_error(exc: Exception) -> bool:
    """A dropped connection or upstream 5xx/429, as opposed to a bad response body.

    Matched on message text rather than exception type because the failure surfaces from
    several layers (httpx, the OpenAI SDK, OpenRouter itself) with no shared base class.
    The observed benchmark failure was httpx's "peer closed connection without sending
    complete message body (incomplete chunked read)" mid-stream.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(
        marker in text
        for marker in (
            "peer closed connection",
            "incomplete chunked read",
            "connection reset",
            "connection error",
            "server disconnected",
            "remote protocol error",
            "timeout",
            "timed out",
            "temporarily unavailable",
            "429",
            "500",
            "502",
            "503",
            "504",
        )
    )


async def _stream_with_transport_retry(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    on_thinking: Callable[[str], Awaitable[None]] | None,
    name: str | None,
) -> str:
    """Retry the streaming call when the transport fails, not the schema.

    ``LLM_MAX_RETRIES`` governs schema repair — it only engages once a response body exists.
    A connection dropped mid-stream produces no body at all, so it bypassed that loop entirely
    and propagated as a hard clause failure. On a five-company benchmark run this cost 30 of
    190 clauses, every one of them to the same dropped-connection error, with three workers
    streaming concurrently.
    """
    last: Exception | None = None
    for attempt in range(1, _TRANSPORT_ATTEMPTS + 1):
        try:
            return await stream_with_reasoning(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                on_thinking=on_thinking,
                name=name,
            )
        except Exception as exc:  # re-raised below unless retryable
            if not _is_transport_error(exc) or attempt == _TRANSPORT_ATTEMPTS:
                raise
            last = exc
            delay = _TRANSPORT_BACKOFF_SECONDS * attempt
            logger.warning(
                "LLM transport failure — retrying",
                name=name,
                attempt=attempt,
                max_attempts=_TRANSPORT_ATTEMPTS,
                delay_seconds=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)
    raise last if last else RuntimeError("unreachable")


async def stream_structured(
    *,
    model: str,
    messages: list[dict[str, Any]],
    schema: type[SchemaT],
    temperature: float = 0.0,
    max_tokens: int = 8192,
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
    retries: int | None = None,
    name: str | None = None,
) -> SchemaT:
    """Stream a completion and validate it against ``schema``, repairing on failure.

    The first attempt streams (preserving reasoning-token callbacks for the UI) and is
    retried on a transport failure (dropped connection, timeout, upstream 5xx/429) — see
    ``_stream_with_transport_retry``. Repair attempts, once a response body exists but fails
    schema validation, use a non-streaming call since they are a short-lived fallback path,
    not the primary UX.
    """
    max_retries = settings.LLM_MAX_RETRIES if retries is None else retries

    raw = await _stream_with_transport_retry(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        on_thinking=on_thinking,
        name=name,
    )

    attempt_messages = list(messages)
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            data = json.loads(raw)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            logger.warning(
                "Structured output validation failed",
                name=name,
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(exc),
            )
            if attempt >= max_retries:
                break
            attempt_messages = [
                *attempt_messages,
                {"role": "assistant", "content": raw},
                _repair_message(raw, str(exc), schema),
            ]
            response = await complete(
                model=model,
                messages=attempt_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                name=f"{name}_repair" if name else "structured_repair",
            )
            raw = response.choices[0].message.content or ""

    raise StructuredOutputError(
        f"Failed to obtain schema-valid JSON for '{name}' after {max_retries + 1} attempts: {last_error}",
        last_raw=raw,
    )
