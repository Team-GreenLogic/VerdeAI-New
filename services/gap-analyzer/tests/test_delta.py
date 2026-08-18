"""Unit tests for delta re-analysis affected-clause detection (app.actors)."""

from datetime import datetime, timezone

import pytest

import app.actors as actors
from verdeai_shared.settings import settings


class _FakeChunks:
    def __init__(self, removed_doc_ids):
        self._removed = removed_doc_ids

    async def distinct(self, field, query):
        # Only the "removed since baseline" query is exercised here.
        assert field == "document_id"
        assert query.get("superseded") is True
        return list(self._removed)


class _FakeDB:
    def __init__(self, removed_doc_ids=()):
        self.chunks = _FakeChunks(removed_doc_ids)


BASELINE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _clause(cid):
    return {"clause_id": cid, "title": f"Clause {cid}", "requirements": "req", "search_query": f"q{cid}"}


@pytest.fixture(autouse=True)
def _stub_retrieval(monkeypatch):
    """Default: no new evidence for any clause (category A finds nothing)."""
    async def _embed(_text):
        return [0.0]

    async def _retrieve(_db, _tenant, _q, _vec, created_after=None):
        return []

    monkeypatch.setattr(actors, "embed_query", _embed)
    monkeypatch.setattr(actors, "hybrid_retrieve", _retrieve)


@pytest.mark.asyncio
async def test_category_b_removed_evidence(monkeypatch):
    """A clause whose parent verdict cited a now-removed document is affected."""
    db = _FakeDB(removed_doc_ids={"docX"})
    clauses = [_clause("4.1"), _clause("4.2")]
    parent_results = [
        {"clause_id": "4.1", "decision": "Met", "source_document_ids": ["docX", "docY"]},
        {"clause_id": "4.2", "decision": "Met", "source_document_ids": ["docZ"]},
    ]
    affected = await actors._compute_affected_clauses(db, "t", BASELINE, clauses, parent_results)
    assert affected == {"4.1"}


@pytest.mark.asyncio
async def test_category_a_new_evidence(monkeypatch):
    """A clause with enough relevant NEW chunks is affected."""
    db = _FakeDB()
    clauses = [_clause("4.1"), _clause("4.2")]
    parent_results = [
        {"clause_id": "4.1", "decision": "Not Met", "source_document_ids": []},
        {"clause_id": "4.2", "decision": "Not Met", "source_document_ids": []},
    ]

    async def _retrieve(_db, _tenant, q, _vec, created_after=None):
        assert created_after == BASELINE  # new-evidence-only retrieval
        if q == "q4.1":
            # MIN_RELEVANT_CHUNKS relevant hits above the rerank floor
            return [{"rerank_score": 0.9}] * settings.MIN_RELEVANT_CHUNKS
        return [{"rerank_score": 0.1}]  # below RERANK_SCORE_THRESHOLD → ignored

    monkeypatch.setattr(actors, "hybrid_retrieve", _retrieve)

    affected = await actors._compute_affected_clauses(db, "t", BASELINE, clauses, parent_results)
    assert affected == {"4.1"}


@pytest.mark.asyncio
async def test_clause_missing_parent_verdict_is_affected():
    """A clause with no parent verdict must be analysed fresh."""
    db = _FakeDB()
    clauses = [_clause("4.1"), _clause("9.9")]
    parent_results = [{"clause_id": "4.1", "decision": "Met", "source_document_ids": []}]
    affected = await actors._compute_affected_clauses(db, "t", BASELINE, clauses, parent_results)
    assert affected == {"9.9"}


@pytest.mark.asyncio
async def test_no_changes_means_nothing_affected():
    """No removed evidence and no new chunks → no clause re-run."""
    db = _FakeDB()
    clauses = [_clause("4.1"), _clause("4.2")]
    parent_results = [
        {"clause_id": "4.1", "decision": "Met", "source_document_ids": ["d1"]},
        {"clause_id": "4.2", "decision": "Met", "source_document_ids": ["d2"]},
    ]
    affected = await actors._compute_affected_clauses(db, "t", BASELINE, clauses, parent_results)
    assert affected == set()
