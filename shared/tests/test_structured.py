"""Tests for stream_structured — schema validation + bounded repair retries."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from verdeai_shared.llm import openrouter_client
from verdeai_shared.llm.structured import StructuredOutputError, stream_structured


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
