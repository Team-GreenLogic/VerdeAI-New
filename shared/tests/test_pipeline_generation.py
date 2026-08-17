"""Tests for generate_missing_requests / generate_recommendations.

Regression coverage for two bugs found in production:
1. Both functions queried the global iso_clauses/iso_state_template collections
   without the analysis's actual version_id, defaulting to DEFAULT_VERSION_ID —
   silently finding nothing for any analysis run against a custom-built ISO
   version. Fixed by threading version_id through.
2. recommend_system.j2 asked for a bare JSON array while the LLM call enforced
   response_format=json_object (which requires a top-level object) — a direct
   contradiction. Fixed by switching the prompt + parser to {"recommendations": [...]}.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

import verdeai_shared.pipeline.missing_requests as missing_requests_module
import verdeai_shared.pipeline.recommendations as recommendations_module
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID
from verdeai_shared.pipeline.missing_requests import generate_missing_requests
from verdeai_shared.pipeline.recommendations import generate_recommendations

CUSTOM_VERSION = "custom-v1"


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return self._docs


class _FakeQueryCollection:
    """Exact-match filtering — good enough for equality queries like
    {"version_id": ..., "clause_id": ...}. Queries with operators (e.g. $regex,
    used by org_profile lookups) simply never match, which is fine since those
    tests don't depend on org_profile content.
    """

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def find(self, query: dict[str, Any], *_args: Any, **_kwargs: Any) -> _FakeCursor:
        return _FakeCursor([d for d in self._docs if self._matches(d, query)])

    async def find_one(self, query: dict[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        for d in self._docs:
            if self._matches(d, query):
                return d
        return None

    @staticmethod
    def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
        return all(doc.get(k) == v for k, v in query.items())


class _FakeInsertCollection:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []

    async def insert_many(self, docs: list[dict[str, Any]]) -> None:
        self.inserted.extend(docs)

    async def find_one(self, query: dict[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        for d in self.inserted:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None


class _FakeDB:
    def __init__(self, iso_clauses_docs: list[dict[str, Any]], iso_state_docs: list[dict[str, Any]]) -> None:
        self.iso_clauses = _FakeQueryCollection(iso_clauses_docs)
        self.iso_state_template = _FakeQueryCollection(iso_state_docs)
        self.org_profile = _FakeQueryCollection([])
        self.missing_request_store = _FakeInsertCollection()
        self.recommendation_store = _FakeInsertCollection()

    def __getitem__(self, name: str) -> Any:
        return getattr(self, name)


ISO_CLAUSES_DOCS = [{"version_id": CUSTOM_VERSION, "clause_id": "6.1.2", "title": "Environmental aspects"}]
ISO_STATE_DOCS = [
    {
        "version_id": CUSTOM_VERSION,
        "clause_id": "6.1.2",
        "field_path": "6.1.2.gap_identified",
        "label": "Gap identified",
        "field_type": "boolean",
        "default": False,
    },
]


def _completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


# ── generate_missing_requests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_requests_uses_the_passed_version_id(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB(ISO_CLAUSES_DOCS, ISO_STATE_DOCS)
    calls: list[dict[str, Any]] = []

    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return _completion("Please provide the requested evidence.")

    monkeypatch.setattr(missing_requests_module, "complete", fake_complete)

    gap_result = {"clause_id": "6.1.2"}
    await generate_missing_requests(db, "tenant-1", "analysis-1", gap_result, version_id=CUSTOM_VERSION)

    assert len(calls) == 1
    assert len(db.missing_request_store.inserted) == 1
    assert db.missing_request_store.inserted[0]["field_path"] == "6.1.2.gap_identified"


@pytest.mark.asyncio
async def test_missing_requests_default_version_id_finds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the actual bug: data lives under a custom version_id,
    but the function is called without one (as it was before the fix) — it must
    silently no-op rather than crash, reproducing the "No state fields found" path.
    """
    db = _FakeDB(ISO_CLAUSES_DOCS, ISO_STATE_DOCS)

    async def fail_if_called(**_kwargs: Any) -> Any:
        raise AssertionError("LLM should not be called when no state fields are found")

    monkeypatch.setattr(missing_requests_module, "complete", fail_if_called)

    gap_result = {"clause_id": "6.1.2"}
    await generate_missing_requests(db, "tenant-1", "analysis-1", gap_result)  # defaults to DEFAULT_VERSION_ID

    assert db.missing_request_store.inserted == []


def test_default_version_id_is_not_the_custom_version() -> None:
    """Sanity check that the two fixtures actually differ — otherwise the two
    tests above wouldn't be distinguishing anything.
    """
    assert DEFAULT_VERSION_ID != CUSTOM_VERSION


# ── generate_recommendations ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommendations_parses_object_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB(ISO_CLAUSES_DOCS, [])
    content = json.dumps({"recommendations": [{"text": "Do X", "cost": 2, "effort_weeks": 1, "impact": 4}]})

    async def fake_complete(**_kwargs: Any) -> SimpleNamespace:
        return _completion(content)

    monkeypatch.setattr(recommendations_module, "complete", fake_complete)

    gap_result = {"clause_id": "6.1.2", "decision": "Not Met", "missing_evidence": ["aspects register"]}
    await generate_recommendations(db, "tenant-1", "analysis-1", gap_result, version_id=CUSTOM_VERSION)

    assert len(db.recommendation_store.inserted) == 1
    assert db.recommendation_store.inserted[0]["text"] == "Do X"


@pytest.mark.asyncio
async def test_recommendations_parses_bare_array_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive fallback for a model that ignores the object-wrapping instruction."""
    db = _FakeDB(ISO_CLAUSES_DOCS, [])
    content = json.dumps([{"text": "Do Y", "cost": 1, "effort_weeks": 2, "impact": 3}])

    async def fake_complete(**_kwargs: Any) -> SimpleNamespace:
        return _completion(content)

    monkeypatch.setattr(recommendations_module, "complete", fake_complete)

    gap_result = {"clause_id": "6.1.2", "decision": "Not Met", "missing_evidence": []}
    await generate_recommendations(db, "tenant-1", "analysis-1", gap_result, version_id=CUSTOM_VERSION)

    assert len(db.recommendation_store.inserted) == 1
    assert db.recommendation_store.inserted[0]["text"] == "Do Y"


@pytest.mark.asyncio
async def test_recommendations_malformed_json_logs_snippet_and_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the actual contradiction: a bare-array response under
    json_object mode is a real failure mode some models will hit. Must degrade
    gracefully (no persisted recommendation), not raise.
    """
    db = _FakeDB(ISO_CLAUSES_DOCS, [])

    async def fake_complete(**_kwargs: Any) -> SimpleNamespace:
        return _completion("")  # simulates an empty/malformed response

    monkeypatch.setattr(recommendations_module, "complete", fake_complete)

    gap_result = {"clause_id": "6.1.2", "decision": "Not Met", "missing_evidence": []}
    await generate_recommendations(db, "tenant-1", "analysis-1", gap_result, version_id=CUSTOM_VERSION)

    assert db.recommendation_store.inserted == []
