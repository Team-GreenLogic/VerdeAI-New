from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.pipeline.rag import (
    _format_chunks_for_prompt,
    _normalise_analysis_citations,
    _select_detailed_results,
    load_chat_context,
)


class FakeCollection:
    def __init__(self, find_one_results=None, counts=None):
        self.find_one_results = list(find_one_results or [])
        self.counts = list(counts or [])
        self.find_one_calls = []

    async def find_one(self, query, **kwargs):
        self.find_one_calls.append((query, kwargs))
        return self.find_one_results.pop(0) if self.find_one_results else None

    async def count_documents(self, query):
        return self.counts.pop(0) if self.counts else 0


class FakeDB:
    def __init__(self, analyses, chunks):
        self.analyses = analyses
        self.chunks = chunks


@pytest.mark.asyncio
async def test_chat_context_selects_latest_completed_analysis_and_reports_staleness():
    completed_at = datetime(2026, 8, 19, tzinfo=timezone.utc)
    analyses = FakeCollection(find_one_results=[{
        "analysis_id": "analysis-newest-complete",
        "status": "complete",
        "created_at": completed_at,
        "version_id": "iso-14001-2015",
        "scope": "full",
        "gap_count": 4,
    }, {"status": "running"}])
    db = FakeDB(analyses, FakeCollection(counts=[2, 1]))

    context = await load_chat_context(db, "tenant-1", "profile-1")

    assert context["analysis_id"] == "analysis-newest-complete"
    assert context["stale"] is True
    assert context["new_chunk_count"] == 2
    assert context["removed_chunk_count"] == 1
    assert context["newer_analysis_status"] == "running"
    query, options = analyses.find_one_calls[0]
    assert query["status"] == "complete"
    assert options["sort"] == [("created_at", -1)]


@pytest.mark.asyncio
async def test_chat_context_without_completed_analysis_exposes_active_status():
    analyses = FakeCollection(find_one_results=[None, {"status": "pending"}])
    db = FakeDB(analyses, FakeCollection())

    context = await load_chat_context(db, "tenant-1", "profile-1")

    assert context == {
        "has_completed_analysis": False,
        "analysis_id": None,
        "newer_analysis_status": "pending",
        "stale": False,
        "new_chunk_count": 0,
        "removed_chunk_count": 0,
    }


def test_explicit_clause_question_selects_that_clause_for_full_detail():
    results = [
        {"clause_id": "6.1.2", "decision": "Not Met", "reasoning": "Aspects missing"},
        {"clause_id": "7.2", "decision": "Partially Met", "reasoning": "Training incomplete"},
    ]

    selected = _select_detailed_results("What is wrong with clause 7.2?", results, [], [])

    assert [item["clause_id"] for item in selected] == ["7.2"]


def test_broad_question_prioritizes_stored_gap_severity_and_impact():
    results = [
        {"clause_id": "5.1", "decision": "Met", "reasoning": "Leadership"},
        {"clause_id": "7.2", "decision": "Partially Met", "reasoning": "Training"},
        {"clause_id": "6.1.2", "decision": "Not Met", "reasoning": "Aspects"},
    ]
    recs = [{"clause_id": "6.1.2", "text": "Create register", "impact": 5}]

    selected = _select_detailed_results("What are our biggest gaps?", results, recs, [])

    assert [item["clause_id"] for item in selected][:2] == ["6.1.2", "7.2"]


def test_retrieved_documents_receive_stable_source_keys_and_labels():
    prompt, citations = _format_chunks_for_prompt([
        {"filename": "aspects-register.pdf", "page": 4, "text": "Register excerpt"},
    ])

    assert "[Source document-1 | aspects-register.pdf, p.4]" in prompt
    assert citations[0]["source_key"] == "document-1"
    assert citations[0]["display_label"] == "aspects-register.pdf · p.4"


def test_analysis_and_its_evidence_receive_distinct_source_keys():
    citations = _normalise_analysis_citations(
        {"analysis_id": "analysis-1", "version_id": "iso-14001-2015"},
        [{
            "clause_id": "6.1.2",
            "decision": "Not Met",
            "reasoning": "The aspects register is incomplete.",
            "citations": [{
                "type": "chunk",
                "filename": "aspects-register.pdf",
                "page": 4,
                "text": "Register excerpt",
            }],
        }],
    )

    assert [citation["source_key"] for citation in citations] == [
        "analysis-6.1.2",
        "analysis-6.1.2-document-1",
    ]
    assert citations[0]["display_label"] == "Clause 6.1.2 · Not Met"

