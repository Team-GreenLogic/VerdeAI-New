"""End-to-end exercise of the validated LangGraph clause pipeline.

Mocks the network/DB boundary (embed_query, hybrid_retrieve, stream_structured,
Mongo) so the full graph — grade_evidence, slot_fill, gap_analyse,
verify_grounding (with its bounded repair loop), reconcile, persist — runs for
real without any external services. This is the fastest way to catch node-name
/ conditional-edge-map / state-shape mistakes before a Docker rebuild.
"""

from __future__ import annotations

from typing import Any

import pytest
from verdeai_shared.llm.structured import StructuredOutputError

from app.pipeline import analyse_clause as ac


# ── Fake Mongo ────────────────────────────────────────────────────────────────

class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return self._docs


class _FakeCollection:
    def __init__(self) -> None:
        self.upserted: list[dict[str, Any]] = []

    def find(self, *_args: Any, **_kwargs: Any) -> _FakeCursor:
        return _FakeCursor([])

    async def find_one(self, *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        return {"status": "running"}

    async def update_one(self, _filter: dict[str, Any], update: dict[str, Any], **_kwargs: Any) -> None:
        self.upserted.append(update.get("$set", {}))


class _FakeDB:
    def __init__(self) -> None:
        self.analyses = _FakeCollection()
        self.org_profile = _FakeCollection()
        self.documents = _FakeCollection()
        self.result_store = _FakeCollection()

    def __getitem__(self, name: str) -> _FakeCollection:
        return getattr(self, name)


# ── Fixtures ──────────────────────────────────────────────────────────────────

CLAUSE = {
    "clause_id": "6.1.2",
    "title": "Environmental aspects",
    "requirements": (
        "The organization shall determine the environmental aspects of its activities. "
        "The organization shall maintain documented information."
    ),
}

CHUNKS = [
    {"_id": "c1", "document_id": "d1", "page": 3, "filename": "policy.pdf",
     "text": "The org determines environmental aspects annually.", "rerank_score": 0.9},
    {"_id": "c2", "document_id": "d1", "page": 4, "filename": "policy.pdf",
     "text": "Documented information is maintained in the EMS register.", "rerank_score": 0.85},
]


async def _fake_emit(*_args: Any, **_kwargs: Any) -> None:
    """No-op — progress events go to Redis, which isn't available in these tests."""


def _slot_fills(**states: str) -> dict[str, Any]:
    """A slot fill covering every slot CLAUSE synthesizes, all "filled" by default.

    CLAUSE has no generated ``slot_schema``, so ``clause_slot_schema`` derives one slot per
    sentence-split sub-requirement ("6.1.2-1", "6.1.2-2"). Override any of them by slot_id,
    e.g. ``_slot_fills(**{"6.1.2-2": "partially_filled"})``.
    """
    return {
        "slot_fills": [
            {
                "slot_id": slot["slot_id"],
                "state": states.get(slot["slot_id"], "filled"),
                "value": "evidence found",
                "citation_ids": [i],
                "notes": "",
            }
            for i, slot in enumerate(ac.clause_slot_schema(CLAUSE), 1)
        ]
    }


def _install_common_mocks(monkeypatch: pytest.MonkeyPatch, chunks: list[dict[str, Any]]) -> None:
    async def fake_embed_query(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    async def fake_hybrid_retrieve(_db: Any, _tenant_id: str, _query: str, _vector: list[float]) -> list[dict[str, Any]]:
        return list(chunks)

    monkeypatch.setattr(ac, "embed_query", fake_embed_query)
    monkeypatch.setattr(ac, "hybrid_retrieve", fake_hybrid_retrieve)
    monkeypatch.setattr(ac, "emit", _fake_emit)


def _met_verdict(**overrides: Any) -> dict[str, Any]:
    base = {
        "decision": "Met",
        "confidence": 0.9,
        "reasoning": "Chunk 1 confirms aspects are determined; Chunk 2 confirms documented information.",
        "findings": [
            {"req_id": "6.1.2-1", "status": "satisfied", "citation_ids": [1], "notes": "ok"},
            {"req_id": "6.1.2-2", "status": "satisfied", "citation_ids": [2], "notes": "ok"},
        ],
        "citations": [
            {"type": "chunk", "chunk_id": "Chunk 1", "page": 3},
            {"type": "chunk", "chunk_id": "Chunk 2", "page": 4},
        ],
        "missing_evidence": [],
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_pipeline_no_chunks_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_common_mocks(monkeypatch, chunks=[])
    db = _FakeDB()

    result = await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)

    assert result["decision"] == "Insufficient Evidence"
    assert db.result_store.upserted, "expected a persisted result"
    assert db.result_store.upserted[-1]["decision"] == "Insufficient Evidence"


@pytest.mark.asyncio
async def test_pipeline_low_score_chunks_proceed_as_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chunks below the rerank-score floor are used anyway, and the verdict is marked degraded.

    This reverses the earlier "abstain rather than spend LLM calls" behaviour. On the
    five-company benchmark, abstaining cost 18 accuracy points: clauses 8.2 and 9.3 returned
    Insufficient Evidence while the tenant's corpus held Emergency_Response_Plan and
    Management_Review_Minutes. An absolute score floor is not a reliable signal that evidence
    is unusable, so where chunks were retrieved at all the clause is judged on the best of them
    and flagged, rather than silently refusing to answer.
    """
    low_score_chunks = [{**c, "rerank_score": 0.05} for c in CHUNKS]
    _install_common_mocks(monkeypatch, chunks=low_score_chunks)
    monkeypatch.setattr(ac.settings, "EVIDENCE_GRADER_ENABLED", False)
    db = _FakeDB()

    async def fake_stream_structured(*, model: str, messages: list[dict[str, Any]], schema: type, **kwargs: Any) -> Any:
        if schema is ac.SlotFillResult:
            return schema.model_validate(_slot_fills())
        if schema is ac.GapVerdict:
            return schema.model_validate(_met_verdict())
        if schema is ac.GroundednessResult:
            return schema.model_validate({"grounded": True, "unsupported_claims": [], "reason": "ok"})
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr(ac, "stream_structured", fake_stream_structured)

    result = await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)
    assert result["decision"] != "Insufficient Evidence"
    assert result["evidence_status"] == "degraded"


@pytest.mark.asyncio
async def test_pipeline_no_chunks_still_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    """The degraded path must not paper over a genuinely empty retrieval.

    Nothing retrieved means there is nothing to judge, and inventing a verdict there would be
    the failure the abstain path exists to prevent.
    """
    _install_common_mocks(monkeypatch, chunks=[])
    db = _FakeDB()

    async def fail_if_called(**_kwargs: Any) -> Any:
        raise AssertionError("stream_structured should not be called when nothing was retrieved")

    monkeypatch.setattr(ac, "stream_structured", fail_if_called)

    result = await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)
    assert result["decision"] == "Insufficient Evidence"


@pytest.mark.asyncio
async def test_pipeline_happy_path_grounded_met(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_common_mocks(monkeypatch, chunks=CHUNKS)
    monkeypatch.setattr(ac.settings, "EVIDENCE_GRADER_ENABLED", False)  # isolate the path being tested
    db = _FakeDB()

    calls: list[str] = []

    async def fake_stream_structured(*, model: str, messages: list[dict[str, Any]], schema: type, **kwargs: Any) -> Any:
        name = kwargs.get("name", "")
        calls.append(name)
        if schema is ac.SlotFillResult:
            return schema.model_validate(_slot_fills())
        if schema is ac.GapVerdict:
            return schema.model_validate(_met_verdict())
        if schema is ac.GroundednessResult:
            return schema.model_validate({"grounded": True, "unsupported_claims": [], "reason": "ok"})
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr(ac, "stream_structured", fake_stream_structured)

    result = await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)

    assert result["decision"] == "Met"
    assert calls == ["slot_fill", "gap_analyse", "groundedness_judge"]
    assert len(result["citations"]) == 2
    # Persisted citations should be display-enriched with the real filename/text.
    persisted = db.result_store.upserted[-1]
    assert persisted["citations"][0]["filename"] == "policy.pdf"


@pytest.mark.asyncio
async def test_pipeline_fabricated_citation_triggers_repair_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """First verdict cites a non-existent Chunk 9; verify_grounding should send it
    back to gap_analyse once, and the second (clean) verdict should be persisted.
    """
    _install_common_mocks(monkeypatch, chunks=CHUNKS)
    monkeypatch.setattr(ac.settings, "EVIDENCE_GRADER_ENABLED", False)
    db = _FakeDB()

    gap_analyse_call_count = 0

    async def fake_stream_structured(*, model: str, messages: list[dict[str, Any]], schema: type, **kwargs: Any) -> Any:
        nonlocal gap_analyse_call_count
        if schema is ac.SlotFillResult:
            return schema.model_validate(_slot_fills())
        if schema is ac.GapVerdict:
            gap_analyse_call_count += 1
            if gap_analyse_call_count == 1:
                return schema.model_validate(_met_verdict(
                    reasoning="Per Chunk 9, everything is fine.",
                    citations=[{"type": "chunk", "chunk_id": "Chunk 9", "page": 1}],
                ))
            return schema.model_validate(_met_verdict())
        if schema is ac.GroundednessResult:
            return schema.model_validate({"grounded": True, "unsupported_claims": [], "reason": "ok"})
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr(ac, "stream_structured", fake_stream_structured)

    result = await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)

    assert gap_analyse_call_count == 2, "expected exactly one repair retry"
    assert result["decision"] == "Met"
    assert all(c["chunk_id"] != "Chunk 9" for c in result["citations"])


@pytest.mark.asyncio
async def test_pipeline_persistent_ungrounded_verdict_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    """If every attempt keeps citing a fabricated chunk, retries exhaust and the
    clause abstains to Insufficient Evidence rather than persisting a hallucination.
    """
    _install_common_mocks(monkeypatch, chunks=CHUNKS)
    monkeypatch.setattr(ac.settings, "EVIDENCE_GRADER_ENABLED", False)
    monkeypatch.setattr(ac.settings, "MAX_VERIFY_RETRIES", 1)
    db = _FakeDB()

    async def fake_stream_structured(*, model: str, messages: list[dict[str, Any]], schema: type, **kwargs: Any) -> Any:
        if schema is ac.SlotFillResult:
            return schema.model_validate(_slot_fills())
        if schema is ac.GapVerdict:
            return schema.model_validate(_met_verdict(
                reasoning="Per Chunk 9, everything is fine.",
                citations=[{"type": "chunk", "chunk_id": "Chunk 9", "page": 1}],
            ))
        if schema is ac.GroundednessResult:
            return schema.model_validate({"grounded": True, "unsupported_claims": [], "reason": "ok"})
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr(ac, "stream_structured", fake_stream_structured)

    result = await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)

    assert result["decision"] == "Insufficient Evidence"


@pytest.mark.asyncio
async def test_pipeline_reconciles_llm_decision_against_slot_fills(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM claims Met but a required slot came back partially filled — the persisted
    decision should be the one the slot states derive, not the LLM's stated decision.
    """
    _install_common_mocks(monkeypatch, chunks=CHUNKS)
    monkeypatch.setattr(ac.settings, "EVIDENCE_GRADER_ENABLED", False)
    db = _FakeDB()

    async def fake_stream_structured(*, model: str, messages: list[dict[str, Any]], schema: type, **kwargs: Any) -> Any:
        if schema is ac.SlotFillResult:
            return schema.model_validate(_slot_fills(**{"6.1.2-2": "partially_filled"}))
        if schema is ac.GapVerdict:
            return schema.model_validate(_met_verdict())
        if schema is ac.GroundednessResult:
            return schema.model_validate({"grounded": True, "unsupported_claims": [], "reason": "ok"})
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr(ac, "stream_structured", fake_stream_structured)

    result = await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)

    assert result["decision"] == "Partially Met"
    assert "Reconciliation note" in result["reasoning"]
    # Findings are rebuilt from the slots, so materiality reflects the schema's
    # `required` flag rather than anything the model claimed.
    statuses = {f["req_id"]: f["status"] for f in result["findings"]}
    assert statuses == {"6.1.2-1": "satisfied", "6.1.2-2": "partial"}


@pytest.mark.asyncio
async def test_pipeline_unfilled_required_slots_derive_not_met(monkeypatch: pytest.MonkeyPatch) -> None:
    """No required slot could be answered — the clause fails outright, and `material`
    is set from the schema rather than left to the model to volunteer."""
    _install_common_mocks(monkeypatch, chunks=CHUNKS)
    monkeypatch.setattr(ac.settings, "EVIDENCE_GRADER_ENABLED", False)
    db = _FakeDB()

    async def fake_stream_structured(*, model: str, messages: list[dict[str, Any]], schema: type, **kwargs: Any) -> Any:
        if schema is ac.SlotFillResult:
            return schema.model_validate(
                _slot_fills(**{"6.1.2-1": "not_filled", "6.1.2-2": "not_filled"})
            )
        if schema is ac.GapVerdict:
            return schema.model_validate(_met_verdict())
        if schema is ac.GroundednessResult:
            return schema.model_validate({"grounded": True, "unsupported_claims": [], "reason": "ok"})
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr(ac, "stream_structured", fake_stream_structured)

    result = await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)

    assert result["decision"] == "Not Met"
    assert all(f["material"] for f in result["findings"])


@pytest.mark.asyncio
async def test_pipeline_paused_analysis_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_common_mocks(monkeypatch, chunks=CHUNKS)
    monkeypatch.setattr(ac.settings, "EVIDENCE_GRADER_ENABLED", False)
    db = _FakeDB()

    async def fake_stream_structured(*, model: str, messages: list[dict[str, Any]], schema: type, **kwargs: Any) -> Any:
        if schema is ac.SlotFillResult:
            return schema.model_validate(_slot_fills())
        raise AssertionError("gap_analyse should not run once paused")

    monkeypatch.setattr(ac, "stream_structured", fake_stream_structured)

    async def paused_find_one(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "paused"}

    monkeypatch.setattr(db.analyses, "find_one", paused_find_one)

    with pytest.raises(ac.AnalysisPaused):
        await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)


@pytest.mark.asyncio
async def test_slot_fill_hard_failure_propagates_instead_of_degrading(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: previously a state-comparison failure was swallowed to an
    empty {} and gap_analyse still ran, silently producing a verdict from no
    comparison data. It must now propagate so the actor records Error.
    """
    _install_common_mocks(monkeypatch, chunks=CHUNKS)
    monkeypatch.setattr(ac.settings, "EVIDENCE_GRADER_ENABLED", False)
    db = _FakeDB()

    async def failing_stream_structured(*, model: str, messages: list[dict[str, Any]], schema: type, **kwargs: Any) -> Any:
        if schema is ac.SlotFillResult:
            raise StructuredOutputError("simulated hard failure")
        raise AssertionError("gap_analyse should not run when slot_fill fails hard")

    monkeypatch.setattr(ac, "stream_structured", failing_stream_structured)

    with pytest.raises(Exception, match="simulated hard failure"):
        await ac.analyse_clause(db, "tenant-1", "analysis-1", CLAUSE)

    # Nothing should have been persisted — the actor is responsible for recording Error.
    assert db.result_store.upserted == []
