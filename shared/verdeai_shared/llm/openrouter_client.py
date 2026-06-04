"""Single async OpenRouter client — uses openai SDK with OpenRouter base URL."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from loguru import logger

from verdeai_shared.settings import settings

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from openai import AsyncOpenAI  # type: ignore[import-untyped]
        _client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": settings.OPENROUTER_APP_URL,
                "X-Title": settings.OPENROUTER_APP_NAME,
            },
        )
    return _client


async def complete(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    max_tokens: int = 2048,
    response_format: dict[str, Any] | None = None,
    provider: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Send a chat completion request and return the full response."""
    client = _get_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    # Pass OpenRouter-specific extras (provider routing, etc.) via extra_body
    extra_body: dict[str, Any] = {}
    if provider is not None:
        extra_body["provider"] = provider
    if extra:
        extra_body.update(extra)
    if extra_body:
        kwargs["extra_body"] = extra_body
    return await client.chat.completions.create(**kwargs)


async def stream(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    max_tokens: int = 2048,
    provider: dict[str, Any] | None = None,
) -> AsyncGenerator[Any, None]:
    """Stream a chat completion. Yields ChatCompletionChunk objects with .choices."""
    client = _get_client()
    extra_body: dict[str, Any] = {}
    if provider is not None:
        extra_body["provider"] = provider
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        extra_body=extra_body or None,
    )
    async for chunk in response:
        yield chunk


async def stream_with_reasoning(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    max_tokens: int = 2048,
    response_format: dict[str, Any] | None = None,
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """Stream a completion, calling on_thinking for each reasoning_content chunk.

    Returns the full answer text (content tokens only, not reasoning).
    Compatible with response_format json_object — accumulates tokens and returns
    the concatenated string for the caller to JSON-parse.
    """
    client = _get_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    answer_parts: list[str] = []
    first_chunk = True
    response = await client.chat.completions.create(**kwargs)
    async for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        # reasoning_content is a non-standard field that OpenRouter adds for
        # reasoning models (DeepSeek-R1). The OpenAI SDK's ChoiceDelta Pydantic
        # model doesn't declare it, so it lands in model_extra rather than as a
        # direct attribute. Try both locations.
        thinking_chunk: str | None = getattr(delta, "reasoning_content", None)
        if thinking_chunk is None:
            extra: dict[str, Any] = getattr(delta, "model_extra", None) or {}
            thinking_chunk = extra.get("reasoning_content") or extra.get("reasoning")

        if first_chunk:
            logger.debug(
                "stream_with_reasoning first chunk",
                delta_keys=list(vars(delta).keys()) if hasattr(delta, "__dict__") else "no-dict",
                model_extra=getattr(delta, "model_extra", None),
                thinking_chunk_present=thinking_chunk is not None,
            )
            first_chunk = False

        if on_thinking and thinking_chunk:
            await on_thinking(thinking_chunk)
        if delta.content:
            answer_parts.append(delta.content)
    return "".join(answer_parts)


async def aclose() -> None:
    """Close the HTTP client (register as shutdown hook in each service main.py)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
