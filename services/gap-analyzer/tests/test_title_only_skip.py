"""Actor-level test: title-only ISO clauses (6.1, 6.2, 7.4, 7.5, 9.1, 9.2 — see
verdeai_shared.iso.slots.clause_slot_schema) must never reach analyse_clause, and must get
their decision entirely from post-loop aggregation.

Uses a minimal in-memory fake Mongo (stateful, unlike test_pipeline_e2e.py's fakes — this
test needs upserts to actually be visible to the later aggregation reads in the same run)
rather than the real stack, so it runs without Docker/RabbitMQ/Redis.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

import app.actors as actors
from verdeai_shared.messaging.events import AnalysisRequested


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return list(self._docs)


def _matches(doc: dict[str, Any], filt: dict[str, Any]) -> bool:
    for k, v in filt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _FakeCollection:
    """Enough of Motor's async collection interface for actors.py's own code paths —
    not a general-purpose Mongo simulator."""

    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self._docs = list(docs or [])

    async def find_one(self, filt: dict[str, Any] | None = None, *_a: Any, **_k: Any) -> dict[str, Any] | None:
        filt = filt or {}
        for d in self._docs:
            if _matches(d, filt):
                return d
        return None

    async def find_one_and_update(
        self, filt: dict[str, Any], update: dict[str, Any], **_k: Any
    ) -> dict[str, Any] | None:
        for d in self._docs:
            if _matches(d, filt):
                old = dict(d)
                d.update(update.get("$set", {}))
                return old
        return None

    async def update_one(
        self, filt: dict[str, Any], update: dict[str, Any], upsert: bool = False, **_k: Any
    ) -> None:
        for d in self._docs:
            if _matches(d, filt):
                d.update(update.get("$set", {}))
                return
        if upsert:
            new_doc = dict(filt)
            new_doc.update(update.get("$set", {}))
            self._docs.append(new_doc)

    def find(self, filt: dict[str, Any] | None = None, *_a: Any, **_k: Any) -> _FakeCursor:
        filt = filt or {}
        return _FakeCursor([d for d in self._docs if _matches(d, filt)])

    async def delete_many(self, filt: dict[str, Any] | None = None, **_k: Any) -> None:
        filt = filt or {}
        self._docs = [d for d in self._docs if not _matches(d, filt)]


class _FakeDB:
    def __init__(self, clauses: list[dict[str, Any]], analysis_doc: dict[str, Any]) -> None:
        self._collections: dict[str, _FakeCollection] = {
            "analyses": _FakeCollection([analysis_doc]),
            "iso_clauses": _FakeCollection(clauses),
            "result_store": _FakeCollection([]),
            "recommendation_store": _FakeCollection([]),
            "missing_request_store": _FakeCollection([]),
        }

    def __getitem__(self, name: str) -> _FakeCollection:
        return self._collections[name]

    def __getattr__(self, name: str) -> _FakeCollection:
        try:
            return self._collections[name]
        except KeyError:
            raise AttributeError(name)


TENANT = "tenant-1"
ANALYSIS_ID = "analysis-1"
VERSION_ID = "iso-14001-benchmark"

# One title-only parent with two real children, mirroring the 6.2 shape.
CLAUSES = [
    {"clause_id": "6.2", "version_id": VERSION_ID, "title": "Environmental objectives",
     "title_only": True, "requirements": "concatenated child prose"},
    {"clause_id": "6.2.1", "version_id": VERSION_ID, "title": "Environmental objectives",
     "requirements": "req 1"},
    {"clause_id": "6.2.2", "version_id": VERSION_ID, "title": "Planning actions",
     "requirements": "req 2"},
]


@pytest.fixture(autouse=True)
def _stub_infra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything outside Mongo: Redis, RabbitMQ, progress events."""

    class _FakeRedis:
        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(actors.aioredis, "from_url", lambda *_a, **_k: _FakeRedis())

    async def _fake_emit(*_a: Any, **_k: Any) -> None:
        pass

    monkeypatch.setattr(actors, "emit", _fake_emit)
    monkeypatch.setattr(actors, "_publish_gaps_ready", AsyncMock())
    monkeypatch.setattr(actors, "generate_recommendations", AsyncMock())
    monkeypatch.setattr(actors, "generate_missing_requests", AsyncMock())


class _FakeMessage:
    def __init__(self, event: AnalysisRequested) -> None:
        self.body = event.model_dump_json().encode()
        self.redelivered = False


@pytest.mark.asyncio
async def test_title_only_clause_never_reaches_analyse_clause(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB(
        clauses=list(CLAUSES),
        analysis_doc={"analysis_id": ANALYSIS_ID, "tenant_id": TENANT, "status": "pending"},
    )
    monkeypatch.setattr(actors, "get_database", lambda: db)

    seen_clause_ids: list[str] = []

    async def _fake_analyse_clause(
        db_: Any,
        _tenant: str,
        _profile: str,
        _aid: str,
        clause: dict[str, Any],
        **_k: Any,
    ) -> dict[str, Any]:
        cid = clause["clause_id"]
        seen_clause_ids.append(cid)
        # Both real children satisfied — 6.2 should aggregate to Met. The real
        # analyse_clause persists internally (its own LangGraph persist node) before
        # returning — replicate that here, since the fake bypasses the graph entirely.
        result = {"decision": "Met", "confidence": 0.9, "reasoning": "ok", "citations": [],
                  "missing_evidence": [], "slot_fills": [], "slot_schema": []}
        await db_["result_store"].update_one(
            {"tenant_id": _tenant, "analysis_id": _aid, "clause_id": cid},
            {"$set": {**result, "tenant_id": _tenant, "analysis_id": _aid, "clause_id": cid}},
            upsert=True,
        )
        return result

    monkeypatch.setattr(actors, "analyse_clause", _fake_analyse_clause)

    event = AnalysisRequested(
        tenant_id=TENANT,
        profile_id="profile-1",
        analysis_id=ANALYSIS_ID,
        scope="full",
        version_id=VERSION_ID,
    )
    await actors.handle_analysis_requested(_FakeMessage(event))  # type: ignore[arg-type]

    # The title-only parent must never be independently analysed.
    assert "6.2" not in seen_clause_ids
    assert set(seen_clause_ids) == {"6.2.1", "6.2.2"}

    results = {r["clause_id"]: r for r in db["result_store"]._docs}

    # Its entire result comes from aggregation: decision derived, no slot detail of its own.
    assert results["6.2"]["decision"] == "Met"
    assert results["6.2"].get("slot_fills", []) == []
    assert "[Aggregated from sub-clause verdicts" in results["6.2"]["reasoning"]

    # And it got real, pooled detail from its children rather than nothing.
    summary = results["6.2"].get("children_summary")
    assert summary is not None
    assert [c["clause_id"] for c in summary["children"]] == ["6.2.1", "6.2.2"]
