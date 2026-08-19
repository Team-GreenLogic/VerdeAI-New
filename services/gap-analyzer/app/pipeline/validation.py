"""Deterministic grounding + decision-reconciliation helpers.

These are pure functions (no I/O, no LLM calls) so they can be unit tested without
the rest of the stack. They implement the "deterministic provenance grounding"
half of the Docling-Graph-inspired accuracy design: every citation and every
"Chunk N" reference in the model's reasoning must resolve to an actually-retrieved
chunk, and the final decision is derived from grounded per-requirement findings
rather than trusted verbatim from the LLM.
"""

from __future__ import annotations

import re
from typing import Any

from app.pipeline.schemas import Citation, GapVerdict, SubRequirementFinding

_CHUNK_MENTION_RE = re.compile(r"[Cc]hunk\s+(\d+)")
_LOW_EVIDENCE_CONFIDENCE_CAP = 0.5
_MIN_GROUNDED_CHUNKS_FOR_HIGH_CONFIDENCE = 2

# Any decision that asserts a compliance conclusion must point at evidence. "Met" is
# included: an uncited "Met" is the most consequential false positive an audit tool can
# emit, and the gap_analyse prompt already requires evidence of implementation for it.
# "Insufficient Evidence" is the only exemption — by definition it has nothing to cite.
_DECISIONS_REQUIRING_CITATIONS = {"Met", "Not Met", "Partially Met"}


def resolve_citation_chunk_index(chunk_id: str | None) -> int | None:
    """Extract the 0-based chunk index from an LLM-authored chunk_id like "Chunk 3".

    Mirrors the enrichment logic in ``analyse_clause._enrich_citations`` so grounding
    checks and citation enrichment agree on what a given chunk_id resolves to.
    """
    if not chunk_id:
        return None
    match = re.search(r"\d+", str(chunk_id))
    if not match:
        return None
    return int(match.group()) - 1


def extract_cited_chunk_numbers(text: str) -> set[int]:
    """Return the set of 1-based chunk numbers referenced as "Chunk N" in free text."""
    return {int(n) for n in _CHUNK_MENTION_RE.findall(text or "")}


def ground_citations(citations: list[Citation], num_chunks: int) -> tuple[list[Citation], list[str]]:
    """Drop citations that don't resolve to a retrieved chunk.

    Returns (grounded_citations, warnings) — org_profile citations are always kept
    (validated separately against the profile map at enrichment time); chunk
    citations with an out-of-range or unparsable index are dropped and reported.
    """
    grounded: list[Citation] = []
    warnings: list[str] = []
    for c in citations:
        if c.type == "org_profile":
            grounded.append(c)
            continue
        idx = resolve_citation_chunk_index(c.chunk_id)
        if idx is not None and 0 <= idx < num_chunks:
            grounded.append(c)
        else:
            warnings.append(f"Dropped ungrounded citation chunk_id={c.chunk_id!r} (retrieved {num_chunks} chunks)")
    return grounded, warnings


def count_grounded_chunk_citations(citations: list[Citation], num_chunks: int) -> int:
    return sum(
        1
        for c in citations
        if c.type == "chunk"
        and (idx := resolve_citation_chunk_index(c.chunk_id)) is not None
        and 0 <= idx < num_chunks
    )


def check_deterministic_grounding(
    verdict: GapVerdict, num_chunks: int, require_material_for_not_met: bool = True
) -> tuple[bool, list[str]]:
    """Hard, rule-based grounding checks. Returns (passed, reasons_for_failure).

    ``require_material_for_not_met`` is switched off when the clause was assessed by slot
    filling: materiality then comes from the slot schema's ``required`` flag and the
    findings are rebuilt in reconciliation, so there is nothing for the model to record
    and failing it here would send a correct verdict into the repair loop.
    """
    reasons: list[str] = []

    grounded_citations, drop_warnings = ground_citations(verdict.citations, num_chunks)
    reasons.extend(drop_warnings)

    if verdict.decision in _DECISIONS_REQUIRING_CITATIONS and not grounded_citations:
        reasons.append(
            f"Decision '{verdict.decision}' requires at least one grounded citation, found none."
        )

    # Step 2 of the decision order requires the failure to be recorded on a finding. Without
    # this, a "Not Met" with no material finding is silently downgraded by reconciliation;
    # failing here instead routes it into the bounded repair loop so the model can fix it.
    if (
        require_material_for_not_met
        and verdict.decision == "Not Met"
        and not any(f.status == "unmet" and f.material for f in verdict.findings)
    ):
        reasons.append(
            "Decision 'Not Met' requires at least one finding with status='unmet' and material=true."
        )

    fabricated = {n for n in extract_cited_chunk_numbers(verdict.reasoning) if not (1 <= n <= num_chunks)}
    if fabricated:
        reasons.append(f"Reasoning references non-existent chunk(s): {sorted(fabricated)}")

    return (len(reasons) == 0, reasons)


def clamp_confidence_for_evidence(confidence: float, grounded_chunk_count: int) -> float:
    """Cap confidence when too few grounded chunks support the verdict."""
    if grounded_chunk_count < _MIN_GROUNDED_CHUNKS_FOR_HIGH_CONFIDENCE:
        return min(confidence, _LOW_EVIDENCE_CONFIDENCE_CAP)
    return confidence


def _derive_decision_from_findings(findings: list[SubRequirementFinding], grounded_chunk_count: int) -> str:
    """Mirrors the DECISION ORDER in ``gap_analyse_system.j2``.

    Prompt and code express the same four steps, so the deterministic override acts as a
    safety net rather than contradicting the procedure the model was told to follow.

    Step 1 (evidence sufficiency) is handled upstream — ``_route_after_grade`` abstains below
    ``MIN_RELEVANT_CHUNKS``, and ``reconcile_decision`` short-circuits on empty findings.
    """
    # Step 2 — a mandatory requirement demonstrably failed. Fails the clause outright,
    # however many sibling assertions are satisfied.
    if any(f.status == "unmet" and f.material for f in findings):
        return "Not Met" if grounded_chunk_count > 0 else "Insufficient Evidence"
    # Step 3 — everything demonstrated.
    if all(f.status == "satisfied" for f in findings):
        return "Met"
    # Step 4 — default. A non-material unmet finding is a limited defect, not a clause
    # failure: deriving Not Met from it produced the false positives on 4.2 and 7.5.2.
    return "Partially Met"


def reconcile_decision(
    findings: list[SubRequirementFinding],
    llm_decision: str,
    llm_confidence: float,
    grounded_chunk_count: int,
    derived_override: str | None = None,
) -> dict[str, Any]:
    """Reconcile the LLM's decision against a deterministically derived one.

    When the derived decision disagrees with the LLM's stated decision, the derived one
    wins (with reduced confidence) rather than trusting the model verbatim.

    ``derived_override`` supplies that decision from outside — the slot-completeness rule
    in ``verdeai_shared.iso.slots.derive_clause_state``. Without it the decision is derived
    from the findings themselves, which is what clauses assessed before the slot layer, and
    the unit tests covering that path, still rely on.
    """
    confidence = clamp_confidence_for_evidence(llm_confidence, grounded_chunk_count)

    if derived_override is None and not findings:
        return {"decision": llm_decision, "confidence": confidence, "note": None}

    derived = derived_override or _derive_decision_from_findings(findings, grounded_chunk_count)
    if derived == llm_decision:
        return {"decision": llm_decision, "confidence": confidence, "note": None}

    return {
        "decision": derived,
        "confidence": min(confidence, _LOW_EVIDENCE_CONFIDENCE_CAP),
        "note": f"Reconciled: LLM proposed '{llm_decision}', findings imply '{derived}' — using derived decision.",
    }
