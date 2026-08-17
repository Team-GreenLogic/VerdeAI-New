"""Unit tests for the deterministic grounding + reconciliation helpers.

No LLM, no DB — pure logic over Pydantic schemas, so these run without the rest
of the service stack installed.
"""

from app.pipeline.schemas import Citation, GapVerdict, SubRequirementFinding
from app.pipeline.validation import (
    check_deterministic_grounding,
    clamp_confidence_for_evidence,
    count_grounded_chunk_citations,
    extract_cited_chunk_numbers,
    ground_citations,
    reconcile_decision,
    resolve_citation_chunk_index,
)


def test_resolve_citation_chunk_index():
    assert resolve_citation_chunk_index("Chunk 3") == 2
    assert resolve_citation_chunk_index("3") == 2
    assert resolve_citation_chunk_index("chunk_7") == 6
    assert resolve_citation_chunk_index(None) is None
    assert resolve_citation_chunk_index("no-digits-here") is None


def test_extract_cited_chunk_numbers():
    text = "See Chunk 1 and Chunk 4 for evidence; Chunk 4 repeats the point."
    assert extract_cited_chunk_numbers(text) == {1, 4}
    assert extract_cited_chunk_numbers("") == set()


def test_ground_citations_drops_out_of_range_chunk_ids():
    citations = [
        Citation(type="chunk", chunk_id="Chunk 1"),
        Citation(type="chunk", chunk_id="Chunk 99"),  # fabricated — only 3 chunks retrieved
        Citation(type="org_profile", field_path="5.1.gap_identified"),
    ]
    grounded, warnings = ground_citations(citations, num_chunks=3)
    assert len(grounded) == 2
    assert grounded[0].chunk_id == "Chunk 1"
    assert grounded[1].type == "org_profile"
    assert len(warnings) == 1
    assert "Chunk 99" in warnings[0]


def test_count_grounded_chunk_citations():
    citations = [
        Citation(type="chunk", chunk_id="Chunk 1"),
        Citation(type="chunk", chunk_id="Chunk 2"),
        Citation(type="chunk", chunk_id="Chunk 50"),
        Citation(type="org_profile", field_path="x"),
    ]
    assert count_grounded_chunk_citations(citations, num_chunks=2) == 2


def test_deterministic_grounding_rejects_empty_citations_for_not_met():
    verdict = GapVerdict(
        decision="Not Met",
        confidence=0.8,
        reasoning="The organisation has no documented policy.",
        citations=[],
    )
    passed, reasons = check_deterministic_grounding(verdict, num_chunks=5)
    assert passed is False
    assert any("requires at least one grounded citation" in r for r in reasons)


def test_deterministic_grounding_rejects_fabricated_chunk_reference():
    verdict = GapVerdict(
        decision="Not Met",
        confidence=0.8,
        reasoning="Per Chunk 12, the policy is missing.",
        citations=[Citation(type="chunk", chunk_id="Chunk 1")],
    )
    passed, reasons = check_deterministic_grounding(verdict, num_chunks=3)
    assert passed is False
    assert any("non-existent chunk" in r for r in reasons)


def test_deterministic_grounding_passes_well_formed_verdict():
    verdict = GapVerdict(
        decision="Met",
        confidence=0.9,
        reasoning="Chunk 1 confirms the policy is documented and communicated.",
        citations=[Citation(type="chunk", chunk_id="Chunk 1")],
    )
    passed, reasons = check_deterministic_grounding(verdict, num_chunks=2)
    assert passed is True
    assert reasons == []


def test_clamp_confidence_for_evidence():
    assert clamp_confidence_for_evidence(0.95, grounded_chunk_count=0) == 0.5
    assert clamp_confidence_for_evidence(0.95, grounded_chunk_count=1) == 0.5
    assert clamp_confidence_for_evidence(0.95, grounded_chunk_count=2) == 0.95
    assert clamp_confidence_for_evidence(0.3, grounded_chunk_count=0) == 0.3  # never raises confidence


def test_reconcile_decision_no_findings_trusts_llm_but_still_clamps():
    result = reconcile_decision([], llm_decision="Met", llm_confidence=0.9, grounded_chunk_count=1)
    assert result["decision"] == "Met"
    assert result["confidence"] == 0.5  # clamped: only 1 grounded chunk
    assert result["note"] is None


def test_reconcile_decision_all_satisfied_matches_met():
    findings = [
        SubRequirementFinding(req_id="4.1-1", status="satisfied", citation_ids=[1]),
        SubRequirementFinding(req_id="4.1-2", status="satisfied", citation_ids=[2]),
    ]
    result = reconcile_decision(findings, llm_decision="Met", llm_confidence=0.9, grounded_chunk_count=3)
    assert result["decision"] == "Met"
    assert result["confidence"] == 0.9
    assert result["note"] is None


def test_reconcile_decision_overrides_llm_when_findings_disagree():
    # LLM says Met, but one finding is unmet — findings should win.
    findings = [
        SubRequirementFinding(req_id="6.1.2-1", status="satisfied", citation_ids=[1]),
        SubRequirementFinding(req_id="6.1.2-2", status="unmet", citation_ids=[]),
    ]
    result = reconcile_decision(findings, llm_decision="Met", llm_confidence=0.95, grounded_chunk_count=3)
    assert result["decision"] == "Partially Met"
    assert result["confidence"] <= 0.5
    assert "Reconciled" in result["note"]


def test_reconcile_decision_all_unmet_no_evidence_is_insufficient():
    findings = [SubRequirementFinding(req_id="9.2.1-1", status="unmet", citation_ids=[])]
    result = reconcile_decision(findings, llm_decision="Not Met", llm_confidence=0.7, grounded_chunk_count=0)
    assert result["decision"] == "Insufficient Evidence"


def test_reconcile_decision_all_unmet_with_evidence_is_not_met():
    findings = [SubRequirementFinding(req_id="9.2.1-1", status="unmet", citation_ids=[1])]
    result = reconcile_decision(findings, llm_decision="Not Met", llm_confidence=0.7, grounded_chunk_count=2)
    assert result["decision"] == "Not Met"
    assert result["note"] is None
