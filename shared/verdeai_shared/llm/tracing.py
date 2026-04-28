"""Langfuse tracing decorator for LLM calls."""

import functools
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def trace(name: str | None = None) -> Callable[[F], F]:
    """Decorator that wraps an async function in a Langfuse generation span."""
    def decorator(fn: F) -> F:
        span_name = name or fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                from langfuse import Langfuse  # type: ignore[import-untyped]
                lf = Langfuse()
                trace_obj = lf.trace(name=span_name)
                generation = trace_obj.generation(name=span_name)
                result = await fn(*args, **kwargs)
                generation.end()
                return result
            except Exception:
                # Tracing failure must never break the LLM call
                return await fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
