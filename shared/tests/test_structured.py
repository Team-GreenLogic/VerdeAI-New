"""Tests for stream_structured — schema validation + bounded repair retries."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from verdeai_shared.llm import openrouter_client, structured
from verdeai_shared.llm.structured import (
    StructuredOutputError,
    _is_transport_error,
    stream_structured,
)


class _Schema(BaseModel):
    decision: str
    confidence: float


def _make_chunk(content: str | None = None) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, reasoning_content=None, model_extra={})
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


class _FakeStreamResponse:
    """Yields the given text as a single content chunk."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._sent = False

    def __aiter__(self) -> "_FakeStreamResponse":
        return self

    async def __anext__(self) -> SimpleNamespace:
        if self._sent:
            raise StopAsyncIteration
        self._sent = True
        return _make_chunk(content=self._text)


class _FakeNonStreamResponse:
    def __init__(self, text: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=text))]


class _FakeClient:
    """Fake OpenAI-compatible client: pops canned answers off two queues."""

    def __init__(self, stream_answers: list[str], complete_answers: list[str]) -> None:
        self._stream_answers = list(stream_answers)
        self._complete_answers = list(complete_answers)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: object) -> object:
        if kwargs.get("stream"):
            return _FakeStreamResponse(self._stream_answers.pop(0))
        return _FakeNonStreamResponse(self._complete_answers.pop(0))


@pytest.mark.asyncio
async def test_stream_structured_succeeds_first_try(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(
        stream_answers=[json.dumps({"decision": "Met", "confidence": 0.9})],
        complete_answers=[],
    )
    monkeypatch.setattr(openrouter_client, "_get_client", lambda: fake)

    result = await stream_structured(
        model="test-model",
        messages=[{"role": "user", "content": "go"}],
        schema=_Schema,
        name="test",
    )
    assert result.decision == "Met"
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_stream_structured_repairs_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(
        stream_answers=["not json at all"],
        complete_answers=[json.dumps({"decision": "Not Met", "confidence": 0.4})],
    )
    monkeypatch.setattr(openrouter_client, "_get_client", lambda: fake)

    result = await stream_structured(
        model="test-model",
        messages=[{"role": "user", "content": "go"}],
        schema=_Schema,
        name="test",
        retries=2,
    )
    assert result.decision == "Not Met"
    assert result.confidence == 0.4


@pytest.mark.asyncio
async def test_stream_structured_repairs_schema_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Valid JSON but missing a required field on the first attempt.
    fake = _FakeClient(
        stream_answers=[json.dumps({"decision": "Met"})],
        complete_answers=[json.dumps({"decision": "Met", "confidence": 0.7})],
    )
    monkeypatch.setattr(openrouter_client, "_get_client", lambda: fake)

    result = await stream_structured(
        model="test-model",
        messages=[{"role": "user", "content": "go"}],
        schema=_Schema,
        name="test",
        retries=1,
    )
    assert result.confidence == 0.7


@pytest.mark.asyncio
async def test_stream_structured_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(
        stream_answers=["garbage"],
        complete_answers=["still garbage", "still garbage again"],
    )
    monkeypatch.setattr(openrouter_client, "_get_client", lambda: fake)

    with pytest.raises(StructuredOutputError):
        await stream_structured(
            model="test-model",
            messages=[{"role": "user", "content": "go"}],
            schema=_Schema,
            name="test",
            retries=2,
        )


# ── Transport-level retry ───────────────────────────────────────────────────
#
# A connection dropped mid-stream (or a timeout, or an upstream 5xx/429) produces no
# response body at all, so it never reaches the JSON-repair loop above and previously
# propagated as a hard clause failure. Reproduced live: 30 of 190 clauses failed identically
# on "peer closed connection without sending complete message body" during a benchmark run
# with three workers streaming concurrently. `_stream_with_transport_retry` retries those
# specifically, leaving a genuine bad-JSON response (still no exception) to the existing loop.


def test_is_transport_error_matches_known_failure_modes() -> None:
    assert _is_transport_error(
        RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)")
    )
    assert _is_transport_error(TimeoutError("Request timed out"))
    assert _is_transport_error(RuntimeError("Server disconnected without sending a response"))
    assert _is_transport_error(RuntimeError("upstream returned 503"))


def test_is_transport_error_does_not_match_content_errors() -> None:
    # A malformed body is a real response — the JSON-repair loop handles it, not this one.
    assert not _is_transport_error(ValueError("Expecting value: line 1 column 1 (char 0)"))
    assert not _is_transport_error(KeyError("decision"))


@pytest.mark.asyncio
async def test_stream_structured_retries_dropped_connection_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    async def flaky_stream(**kwargs: object) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("peer closed connection without sending complete message body")
        return json.dumps({"decision": "Met", "confidence": 0.9})

    monkeypatch.setattr(structured, "stream_with_reasoning", flaky_stream)
    monkeypatch.setattr(structured, "_TRANSPORT_BACKOFF_SECONDS", 0.0)

    result = await stream_structured(
        model="test-model",
        messages=[{"role": "user", "content": "go"}],
        schema=_Schema,
        name="test",
    )
    assert result.decision == "Met"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_stream_structured_gives_up_after_repeated_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def always_drops(**kwargs: object) -> str:
        raise RuntimeError("peer closed connection without sending complete message body")

    monkeypatch.setattr(structured, "stream_with_reasoning", always_drops)
    monkeypatch.setattr(structured, "_TRANSPORT_BACKOFF_SECONDS", 0.0)

    with pytest.raises(RuntimeError, match="peer closed connection"):
        await stream_structured(
            model="test-model",
            messages=[{"role": "user", "content": "go"}],
            schema=_Schema,
            name="test",
        )


@pytest.mark.asyncio
async def test_stream_structured_does_not_retry_non_transport_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bug in our own code (e.g. a TypeError) must fail fast, not burn 3 retries."""
    calls = {"n": 0}

    async def broken(**kwargs: object) -> str:
        calls["n"] += 1
        raise TypeError("unexpected keyword argument")

    monkeypatch.setattr(structured, "stream_with_reasoning", broken)

    with pytest.raises(TypeError):
        await stream_structured(
            model="test-model",
            messages=[{"role": "user", "content": "go"}],
            schema=_Schema,
            name="test",
        )
    assert calls["n"] == 1
