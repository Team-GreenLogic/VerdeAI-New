"""Per-clause gap analysis pipeline — LangGraph StateGraph.

Each ISO clause is analysed through a validated pipeline:
  embed → retrieve → grade_evidence → [conditional]
                       ├─ (enough relevant evidence) → load_org_profile → load_slot_schema
                       │      → slot_fill → gap_analyse → verify_grounding → [conditional]
                       │            ├─ (grounded)            → reconcile → persist → END
                       │            ├─ (ungrounded, retries left) → gap_analyse  (repair loop)
                       │            └─ (ungrounded, exhausted)  → insufficient_persist → END
                       └─ (not enough relevant evidence)   → insufficient_persist → END

Two accuracy principles run throughout: every LLM call returns schema-validated,
repair-retried JSON (``verdeai_shared.llm.structured.stream_structured``), and every
citation / "Chunk N" reference is deterministically checked against the actually
retrieved evidence before a verdict is persisted (``app.pipeline.validation``) —
verdicts that can't be grounded are downgraded to Insufficient Evidence rather than
persisted as a hallucinated Met/Not Met/Partially Met.

Each node emits a ``clause_stage`` progress event before executing,
giving the frontend step-by-step visibility within a clause.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypedDict

import verdeai_shared as _vs_pkg
from bson import ObjectId
from jinja2 import Environment, FileSystemLoader
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from loguru import logger

from verdeai_shared.db.repositories.result_store import ResultStoreRepository
from verdeai_shared.iso.slots import (
    SlotFillResult,
    clause_slot_schema,
    score_clause,
    slot_fills_to_findings,
)
from verdeai_shared.llm.structured import stream_structured
from verdeai_shared.retrieval.embedder import embed_query
from verdeai_shared.retrieval.hybrid import hybrid_retrieve
from verdeai_shared.settings import settings

from app.pipeline.schemas import EvidenceGrade, GapVerdict, GroundednessResult, SubRequirementFinding
from app.pipeline.validation import (
    check_deterministic_grounding,
    count_grounded_chunk_citations,
    ground_citations,
    reconcile_decision,
)
from app.progress import emit

try:
    from langfuse.decorators import langfuse_context, observe  # type: ignore[import-untyped]
    _LANGFUSE = True
except ImportError:
    _LANGFUSE = False
    def observe(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore[misc]
        return lambda fn: fn

_PROMPTS_DIR = Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


class AnalysisPaused(Exception):
    """Raised when a pause flag is detected mid-clause."""


_INSUFFICIENT: dict[str, Any] = {
    "decision": "Insufficient Evidence",
    "confidence": 0.0,
    "reasoning": "No relevant document chunks found in the tenant knowledge base for this clause.",
    "citations": [],
    "missing_evidence": ["Upload and process relevant compliance documents to enable gap analysis."],
}

# ── Step registry ─────────────────────────────────────────────────────────────
# Single source of truth: (machine_name, human_label) pairs in execution order.
_STEPS: list[tuple[str, str]] = [
    ("embed",             "Embedding clause text…"),
    ("retrieve",          "Retrieving relevant evidence…"),
    ("grade_evidence",    "Grading evidence relevance…"),
    ("load_profile",      "Loading organisation profile…"),
    ("load_template",     "Loading ISO requirement slots…"),
    ("state_compare",     "Filling requirement slots from evidence…"),
    ("gap_analyse",       "Running gap analysis…"),
    ("verify_grounding",  "Verifying evidence grounding…"),
    ("reconcile",         "Reconciling final decision…"),
    ("persist",           "Persisting result…"),
]
_STEP_TOTAL = len(_STEPS)
# name → (1-based index, human label)
_STEP_MAP: dict[str, tuple[int, str]] = {
    name: (i + 1, label) for i, (name, label) in enumerate(_STEPS)
}


# ── LangGraph state ───────────────────────────────────────────────────────────

class ClauseState(TypedDict, total=False):
    """Data flowing between nodes.

    Infra objects (db, redis, callbacks) stay in ``config["configurable"]``
    to remain serialisation-safe if a checkpointer is ever added later.
    """

    clause: dict[str, Any]
    query_text: str
    query_vector: list[float]
    chunks: list[dict[str, Any]]
    evidence_text: str
    org_profile_map: dict[str, Any]
    evidence_status: str
    slot_schema: list[dict[str, Any]]
    slot_fills: list[dict[str, Any]]
    gap_result: dict[str, Any]
    verify_attempts: int
    grounding_passed: bool
    grounding_feedback: str | None


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_query_text(clause: dict[str, Any]) -> str:
    """Prefer the LLM-generated retrieval query (phrased for semantic search over
    company documents); fall back to title+requirements for clauses extracted
    before this field existed (e.g. hardcoded seed clauses)."""
    search_query = clause.get("search_query") or ""
    if search_query:
        return search_query
    return f"{clause.get('title', clause.get('clause_id', ''))}\n{clause.get('requirements', '')}"


def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    """Number chunks 1..N for display. ``text`` already carries the ingestion-time
    contextual preamble (stored as "CONTEXT: {preamble}\\n\\n{chunk_text}" — see
    document-processor stage3_chunk.py), so the analysis LLM sees the same context
    the reranker scored against.
    """
    parts = []
    for i, c in enumerate(chunks, 1):
        page = c.get("page", "?")
        filename = c.get("filename", "unknown")
        text = c.get("text", "")
        parts.append(f"[Chunk {i} | {filename}, p.{page}]\n{text}")
    return "\n\n---\n\n".join(parts)


async def _enrich_chunks_with_filenames(
    db: Any, tenant_id: str, chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach filenames to retrieved chunks — chunks only store document_id."""
    doc_ids = [c.get("document_id") for c in chunks if c.get("document_id")]
    if not doc_ids:
        return chunks

    try:
        object_ids = [ObjectId(d) for d in doc_ids]
    except Exception:
        return chunks

    cursor = db.documents.find(
        {"tenant_id": tenant_id, "_id": {"$in": object_ids}},
        {"_id": 1, "filename": 1},
    )
    docs = await cursor.to_list(length=None)
    id_to_filename = {str(d["_id"]): d.get("filename", "unknown") for d in docs}

    return [{**c, "filename": id_to_filename.get(str(c.get("document_id", "")), "unknown")} for c in chunks]


def _enrich_citations(
    chunks: list[dict[str, Any]], org_profile_map: dict[str, Any], citations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach the actual excerpt text to already-grounded citations so the frontend
    can show the source content on click, instead of just a chunk position/page.
    Citations reaching this point have already passed deterministic grounding in
    ``verify_grounding`` / ``reconcile`` — this is display enrichment, not validation.
    """
    from app.pipeline.validation import resolve_citation_chunk_index

    enriched: list[dict[str, Any]] = []
    for citation in citations:
        c = dict(citation)
        if c.get("type") == "chunk":
            idx = resolve_citation_chunk_index(c.get("chunk_id"))
            if idx is not None and 0 <= idx < len(chunks):
                chunk = chunks[idx]
                c["filename"] = chunk.get("filename", "unknown")
                c["page"] = chunk.get("page", c.get("page"))
                c["text"] = chunk.get("text", "")
        elif c.get("type") == "org_profile":
            c["text"] = str(org_profile_map.get(c.get("field_path", ""), ""))
        enriched.append(c)
    return enriched


async def _emit_step(step_name: str, config: RunnableConfig) -> None:
    """Broadcast a clause_stage progress event for the given step."""
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    step_index, label = _STEP_MAP[step_name]
    await emit(
        cfg["tenant_id"],
        cfg["analysis_id"],
        "clause_stage",
        "progress",
        label,
        clause_id=cfg.get("clause_id"),
        step=step_name,
        step_index=step_index,
        step_total=_STEP_TOTAL,
        redis_client=cfg.get("redis_client"),
    )


# ── Nodes ─────────────────────────────────────────────────────────────────────

@observe(as_type="span")  # type: ignore[misc]
async def _embed_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("embed", config)
    clause = state["clause"]
    query_text = build_query_text(clause)
    # Let exceptions propagate — the actor catches them and records a proper Error
    # decision rather than silently cascading Insufficient Evidence to all remaining clauses.
    vector: list[float] = await embed_query(query_text)
    return {"query_vector": vector, "query_text": query_text}


@observe(as_type="span")  # type: ignore[misc]
async def _retrieve_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("retrieve", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    query_text = state["query_text"]
    # Let exceptions propagate so the actor can distinguish a retrieval failure
    # from a genuine "no documents in the knowledge base" result.
    chunks = await hybrid_retrieve(
        cfg["db"], cfg["tenant_id"], cfg["profile_id"], query_text, state["query_vector"]
    )
    if chunks:
        chunks = await _enrich_chunks_with_filenames(cfg["db"], cfg["tenant_id"], chunks)
    return {"chunks": chunks}


@observe(as_type="generation")  # type: ignore[misc]
async def _grade_evidence_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    """CRAG-style evidence filtering: drop chunks below the rerank-score floor,
    then (optionally) an LLM relevance grader narrows further. This is what
    prevents the LLM from being handed a fixed top-N of marginal/irrelevant
    chunks regardless of quality — the previous behaviour, since rerank scores
    were computed and discarded (see shared/verdeai_shared/retrieval/hybrid.py).
    """
    await _emit_step("grade_evidence", config)
    clause = state["clause"]
    clause_id: str = clause["clause_id"]
    chunks = state.get("chunks", [])

    # Missing rerank_score should not occur (hybrid_retrieve always attaches it) —
    # default to keeping the chunk rather than silently dropping on a data-shape surprise.
    score_filtered = [c for c in chunks if c.get("rerank_score", 1.0) >= settings.RERANK_SCORE_THRESHOLD]

    kept = score_filtered
    if settings.EVIDENCE_GRADER_ENABLED and score_filtered:
        try:
            user_prompt = _jinja.get_template("evidence_grader.j2").render(
                clause_id=clause_id,
                clause_title=clause.get("title", clause_id),
                clause_requirements=clause.get("requirements", ""),
                evidence_chunks=_format_chunks(score_filtered),
            )
            grade: EvidenceGrade = await stream_structured(
                model=settings.GRADER_MODEL or settings.CHEAP_REASONING_MODEL,
                messages=[{"role": "user", "content": user_prompt}],
                schema=EvidenceGrade,
                max_tokens=1024,
                name="evidence_grade",
            )
            # Three distinct outcomes. Previously `if grade.relevant_indices:` collapsed the
            # first two, so a grader rejecting EVERYTHING fell through and kept the whole list,
            # while a grader endorsing ONE chunk dropped to 1 and abstained below
            # MIN_RELEVANT_CHUNKS — "all irrelevant" was more permissive than "one relevant".
            relevant = set(grade.relevant_indices)
            kept = [c for i, c in enumerate(score_filtered, 1) if i in relevant]
        except Exception as exc:
            logger.warning(
                "Evidence grading LLM call failed — falling back to rerank-score filter only",
                clause_id=clause_id, error=str(exc),
            )

    # Relative floor. An absolute RERANK_SCORE_THRESHOLD plus a strict grader can starve a
    # clause whose evidence demonstrably exists — benchmark clauses 8.2 and 9.3 abstained while
    # the tenant held Emergency_Response_Plan and Management_Review_Minutes. Where chunks were
    # retrieved at all, keep the best few and mark the verdict degraded rather than abstaining:
    # a flagged weak answer is more useful to an auditor than a silent refusal.
    evidence_status = "sufficient"
    if len(kept) < settings.MIN_RELEVANT_CHUNKS and chunks:
        ranked = sorted(chunks, key=lambda c: c.get("rerank_score", 0.0), reverse=True)
        kept = ranked[: settings.MIN_RELEVANT_CHUNKS]
        evidence_status = "degraded"
        logger.info(
            "Evidence below threshold — proceeding on top-ranked chunks",
            clause_id=clause_id, kept=len(kept), retrieved=len(chunks),
        )
    elif not chunks:
        evidence_status = "none_retrieved"

    evidence_text = _format_chunks(kept) if kept else ""
    return {"chunks": kept, "evidence_text": evidence_text, "evidence_status": evidence_status}


async def _load_org_profile_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("load_profile", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause_id: str = state["clause"]["clause_id"]
    org_cursor = cfg["db"].org_profile.find(
        {
            "tenant_id": cfg["tenant_id"],
            "profile_id": cfg["profile_id"],
            "field_path": {"$regex": f"^{clause_id}\\."},
        }
    )
    org_entries = await org_cursor.to_list(None)
    return {"org_profile_map": {e["field_path"]: e.get("value") for e in org_entries}}


async def _load_slot_schema_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    """Load the slot schema the fill step will answer — what information ISO requires.

    Prefers the clause's generated ``slot_schema`` (see
    ``services/iso-knowledge/app/generate_slot_schemas.py``); ``clause_slot_schema``
    synthesizes one from ``requirements_list`` when a clause has not been migrated,
    so there is a single code path and no un-slotted clause to special-case.
    """
    await _emit_step("load_template", config)
    schema = clause_slot_schema(state["clause"])

    # A schema with no critical slot can never reach Not Met through the gate, only through the
    # low-coverage floor. That is a legitimate shape for a synthesized schema, but for a curated
    # one it means the authored flags never reached the database — which silently disabled the
    # gate across a whole benchmark run once already. Log it rather than let it pass unseen.
    if schema and not any(s.get("critical") for s in schema):
        logger.warning(
            "Clause schema has no critical slot — Not Met reachable only via low coverage",
            clause_id=state["clause"].get("clause_id"),
            slots=len(schema),
        )

    return {"slot_schema": schema}


@observe(as_type="generation")  # type: ignore[misc]
async def _slot_fill_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    """Answer each slot's extraction question from the evidence.

    Deliberately not a compliance judgement: the model records how completely each
    piece of required information could be established, and the clause decision is
    derived from those states in ``_reconcile_node``.
    """
    await _emit_step("state_compare", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause = state["clause"]
    clause_id: str = clause["clause_id"]
    clause_title: str = clause.get("title", clause_id)
    on_thinking: Callable[[str], Awaitable[None]] | None = cfg.get("on_thinking")

    system_prompt = _jinja.get_template("slot_fill_system.j2").render()
    user_prompt = _jinja.get_template("slot_fill_user.j2").render(
        clause_id=clause_id,
        clause_title=clause_title,
        clause_requirements=clause.get("requirements", ""),
        slot_schema_json=json.dumps(state.get("slot_schema", []), indent=2),
        org_profile_json=json.dumps(state.get("org_profile_map", {}), indent=2),
        evidence_chunks=state.get("evidence_text", ""),
    )
    # No try/except here: a hard failure (malformed JSON that can't be repaired, or a
    # transport error) propagates so the actor records a proper Error decision. Degrading
    # to an empty fill would silently derive "Not Met" for the whole clause.
    result: SlotFillResult = await stream_structured(
        model=settings.PRIMARY_REASONING_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        schema=SlotFillResult,
        max_tokens=8192,
        on_thinking=on_thinking,
        name="slot_fill",
    )
    return {"slot_fills": [f.model_dump() for f in result.slot_fills]}


@observe(as_type="generation")  # type: ignore[misc]
async def _gap_analyse_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("gap_analyse", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause = state["clause"]
    clause_id: str = clause["clause_id"]
    clause_title: str = clause.get("title", clause_id)
    on_thinking: Callable[[str], Awaitable[None]] | None = cfg.get("on_thinking")

    # Pause check between LLM calls
    analysis_id: str = cfg["analysis_id"]
    status_doc = await cfg["db"].analyses.find_one({"analysis_id": analysis_id}, {"status": 1})
    if status_doc and status_doc.get("status") == "paused":
        raise AnalysisPaused(analysis_id)

    prior_verdict = cfg.get("prior_verdict")
    system_prompt = _jinja.get_template("gap_analyse_system.j2").render()
    user_prompt = _jinja.get_template("gap_analyse_user.j2").render(
        clause_id=clause_id,
        clause_title=clause_title,
        clause_requirements=clause.get("requirements", ""),
        slot_schema_json=json.dumps(state.get("slot_schema", []), indent=2),
        slot_fills_json=json.dumps(state.get("slot_fills", []), indent=2),
        evidence_chunks=state.get("evidence_text", ""),
        prior_verdict=prior_verdict,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    # Bounded repair loop: verify_grounding routes back here with feedback when
    # the previous verdict cited a non-existent chunk or lacked required citations.
    feedback = state.get("grounding_feedback")
    if feedback:
        messages.append({"role": "assistant", "content": json.dumps(state.get("gap_result", {}))})
        messages.append({"role": "user", "content": (
            "Your previous verdict failed grounding verification:\n"
            f"{feedback}\n\n"
            "Revise the verdict so every citation and every 'Chunk N' mention in 'reasoning' "
            "corresponds to a chunk actually shown in 'Supporting evidence chunks' above. "
            "Return the corrected JSON verdict now."
        )})

    # Let exceptions propagate (including StructuredOutputError after internal
    # repair retries) — an unrecoverable LLM/parse failure is an Error, not a
    # fabricated "Insufficient Evidence" verdict.
    verdict: GapVerdict = await stream_structured(
        model=settings.PRIMARY_REASONING_MODEL,
        messages=messages,
        schema=GapVerdict,
        max_tokens=8192,
        on_thinking=on_thinking,
        name="gap_analyse",
    )
    return {"gap_result": verdict.model_dump(), "grounding_feedback": None}


@observe(as_type="generation")  # type: ignore[misc]
async def _verify_grounding_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    """Deterministic citation/chunk grounding check + an LLM groundedness judge.

    This is the anti-hallucination core: a verdict that cites a fabricated chunk,
    lacks required citations, or that the judge flags as unsupported is either
    sent back for a bounded repair (see gap_analyse's feedback handling) or —
    once retries are exhausted — abandoned in favour of Insufficient Evidence
    rather than persisted.
    """
    await _emit_step("verify_grounding", config)
    clause_id: str = state["clause"]["clause_id"]
    verdict = GapVerdict.model_validate(state.get("gap_result", {}))
    num_chunks = len(state.get("chunks", []))

    # Materiality is a property of the slot schema, not of this verdict, so the "Not Met
    # needs a material unmet finding" rule has nothing to enforce once slots are filled —
    # _reconcile_node derives both the decision and the findings from the slot states.
    det_passed, det_reasons = check_deterministic_grounding(
        verdict, num_chunks, require_material_for_not_met=not state.get("slot_fills")
    )

    judge_grounded = True
    judge_reasons: list[str] = []
    if state.get("chunks"):
        try:
            judge_prompt = _jinja.get_template("groundedness_judge.j2").render(
                evidence_chunks=state.get("evidence_text", ""),
                reasoning=verdict.reasoning,
                findings_json=json.dumps([f.model_dump() for f in verdict.findings], indent=2),
            )
            judge: GroundednessResult = await stream_structured(
                model=settings.GRADER_MODEL or settings.CHEAP_REASONING_MODEL,
                messages=[{"role": "user", "content": judge_prompt}],
                schema=GroundednessResult,
                max_tokens=1024,
                name="groundedness_judge",
            )
            judge_grounded = judge.grounded
            judge_reasons = judge.unsupported_claims
        except Exception as exc:
            logger.warning(
                "Groundedness judge call failed — proceeding on deterministic check only",
                clause_id=clause_id, error=str(exc),
            )

    passed = det_passed and judge_grounded
    attempts = state.get("verify_attempts", 0) + 1

    if passed:
        return {"grounding_passed": True, "verify_attempts": attempts, "grounding_feedback": None}

    reasons = [*det_reasons, *[f"Unsupported claim: {c}" for c in judge_reasons]]
    can_retry = attempts <= settings.MAX_VERIFY_RETRIES
    logger.warning(
        "Grounding verification failed",
        clause_id=clause_id, attempt=attempts, will_retry=can_retry, reasons=reasons,
    )
    return {
        "grounding_passed": False,
        "verify_attempts": attempts,
        "grounding_feedback": "\n".join(reasons) if can_retry else None,
    }


@observe(as_type="span")  # type: ignore[misc]
async def _reconcile_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    """Derive the final decision from slot completeness rather than trusting the LLM's
    stated decision verbatim, and strip any citation that didn't survive grounding.

    The findings are replaced by the slot-derived ones: ``material`` then reflects the
    schema's ``required`` flag instead of a per-run model judgement, which is the whole
    reason the slot layer exists. The model's own findings are still what the groundedness
    judge saw upstream, so nothing is lost by overwriting them here.
    """
    await _emit_step("reconcile", config)
    verdict = GapVerdict.model_validate(state.get("gap_result", {}))
    num_chunks = len(state.get("chunks", []))
    schema = state.get("slot_schema", [])
    fills = state.get("slot_fills", [])

    grounded_citations, _ = ground_citations(verdict.citations, num_chunks)
    grounded_chunk_count = count_grounded_chunk_citations(grounded_citations, num_chunks)

    # An empty schema means the clause carries no requirements text to decompose at all.
    # Scoring zero slots would read as "no required information established", so fall back to
    # the findings-derived decision instead.
    score = None
    if schema:
        findings = [
            SubRequirementFinding.model_validate(f) for f in slot_fills_to_findings(schema, fills)
        ]
        score = score_clause(schema, fills)
        derived: str | None = score.decision
    else:
        findings = verdict.findings
        derived = None

    outcome = reconcile_decision(
        findings,
        verdict.decision,
        verdict.confidence,
        grounded_chunk_count,
        derived_override=derived,
    )

    gap_result = verdict.model_dump()
    gap_result["citations"] = [c.model_dump() for c in grounded_citations]
    gap_result["findings"] = [f.model_dump() for f in findings]
    # Both the answers and the schema they were judged against. Schemas are edited over time,
    # so a result that stored only the fills would later be read against a schema that no
    # longer matches it — the labels, questions and required flags would drift out from under
    # the verdict they produced.
    gap_result["slot_fills"] = fills
    gap_result["slot_schema"] = schema
    gap_result["evidence_status"] = state.get("evidence_status", "sufficient")
    # The arithmetic that produced the decision, stored so the verdict can be re-checked
    # against its own derivation rather than against the prose the model wrote beside it.
    if score is not None:
        gap_result["decision_trace"] = score.model_dump()
    gap_result["decision"] = outcome["decision"]
    gap_result["confidence"] = outcome["confidence"]
    if outcome["note"]:
        gap_result["reasoning"] = f"{gap_result['reasoning']}\n\n[Reconciliation note: {outcome['note']}]"

    return {"gap_result": gap_result}


async def _persist_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("persist", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause_id: str = state["clause"]["clause_id"]
    gap_result = state.get("gap_result", dict(_INSUFFICIENT))
    if gap_result.get("citations"):
        gap_result = {
            **gap_result,
            "citations": _enrich_citations(
                state.get("chunks", []), state.get("org_profile_map", {}), gap_result["citations"]
            ),
        }
    # Provenance: the documents whose chunks were considered for this clause.
    # Delta re-analysis uses this to detect verdicts invalidated by a removed doc.
    gap_result["source_document_ids"] = sorted(
        {c["document_id"] for c in state.get("chunks", []) if c.get("document_id")}
    )
    await ResultStoreRepository(cfg["db"], cfg["tenant_id"]).upsert(
        cfg["analysis_id"], clause_id, gap_result
    )
    logger.info(
        "Clause analysed",
        clause_id=clause_id,
        decision=gap_result.get("decision"),
        confidence=gap_result.get("confidence"),
    )
    return {}


async def _insufficient_persist_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    """Shortcut path when no (or no sufficiently relevant / groundable) evidence
    was available — skip or abandon LLM verdict generation rather than guess.
    """
    await _emit_step("persist", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause_id: str = state["clause"]["clause_id"]
    result = dict(_INSUFFICIENT)
    await ResultStoreRepository(cfg["db"], cfg["tenant_id"]).upsert(
        cfg["analysis_id"], clause_id, result
    )
    logger.info("Insufficient evidence — abstaining", clause_id=clause_id)
    return {"gap_result": result}


# ── Conditional edges ─────────────────────────────────────────────────────────

def _route_after_grade(state: ClauseState) -> str:
    """Route to full pipeline only if enough relevant evidence survived grading."""
    if len(state.get("chunks", [])) >= settings.MIN_RELEVANT_CHUNKS:
        return "load_org_profile"
    return "insufficient_persist"


def _route_after_verify(state: ClauseState) -> str:
    """Route to reconciliation once grounded; otherwise retry (bounded) or abstain."""
    if state.get("grounding_passed"):
        return "reconcile"
    if state.get("grounding_feedback"):
        return "retry"
    return "abstain"


# ── Graph construction ────────────────────────────────────────────────────────

def _build_clause_graph() -> Any:  # returns CompiledStateGraph
    g: StateGraph = StateGraph(ClauseState)  # type: ignore[type-arg]

    g.add_node("embed",                _embed_node)
    g.add_node("retrieve",             _retrieve_node)
    g.add_node("grade_evidence",       _grade_evidence_node)
    g.add_node("load_org_profile",     _load_org_profile_node)
    g.add_node("load_slot_schema",     _load_slot_schema_node)
    g.add_node("slot_fill",            _slot_fill_node)
    g.add_node("gap_analyse",          _gap_analyse_node)
    g.add_node("verify_grounding",     _verify_grounding_node)
    g.add_node("reconcile",            _reconcile_node)
    g.add_node("persist",              _persist_node)
    g.add_node("insufficient_persist", _insufficient_persist_node)

    g.set_entry_point("embed")
    g.add_edge("embed", "retrieve")
    g.add_edge("retrieve", "grade_evidence")

    # If enough relevant evidence survived grading → full pipeline; else abstain
    g.add_conditional_edges(
        "grade_evidence",
        _route_after_grade,
        {
            "load_org_profile":     "load_org_profile",
            "insufficient_persist": "insufficient_persist",
        },
    )

    g.add_edge("load_org_profile",  "load_slot_schema")
    g.add_edge("load_slot_schema",   "slot_fill")
    g.add_edge("slot_fill",          "gap_analyse")
    g.add_edge("gap_analyse",         "verify_grounding")

    # Bounded repair loop: ungrounded verdicts retry gap_analyse with feedback,
    # up to MAX_VERIFY_RETRIES, before falling back to Insufficient Evidence.
    g.add_conditional_edges(
        "verify_grounding",
        _route_after_verify,
        {
            "reconcile":             "reconcile",
            "retry":                 "gap_analyse",
            "abstain":               "insufficient_persist",
        },
    )

    g.add_edge("reconcile",            "persist")
    g.add_edge("persist",              END)
    g.add_edge("insufficient_persist", END)

    # No checkpointer — clause-level recovery via result_store is sufficient.
    return g.compile()


# Module-level singleton — compiled once at import, reused for every clause.
_clause_graph = _build_clause_graph()


# ── Public entry point ────────────────────────────────────────────────────────

@observe(name="analyse_clause")  # type: ignore[misc]
async def analyse_clause(
    db: Any,
    tenant_id: str,
    profile_id: str,
    analysis_id: str,
    clause: dict[str, Any],
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
    redis_client: Any = None,
    prior_verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke the LangGraph clause pipeline. Returns the gap result dict.

    ``prior_verdict`` (delta re-analysis only) is the clause's previous verdict; it
    is shown to the gap_analyse LLM as *reference context* so it can explain what
    changed. It never overrides grounding/reconciliation — the final decision is
    still bound to the evidence actually retrieved this run.
    """
    clause_id = clause.get("clause_id", "")
    if _LANGFUSE:
        try:
            langfuse_context.update_current_trace(  # type: ignore[union-attr]
                name=f"analyse_clause:{clause_id}",
                session_id=tenant_id,
                user_id=tenant_id,
                tags=["gap-analysis", clause_id],
                metadata={"analysis_id": analysis_id, "clause_id": clause_id},
            )
        except Exception:
            pass

    config: RunnableConfig = {
        "configurable": {
            "db": db,
            "tenant_id": tenant_id,
            "profile_id": profile_id,
            "analysis_id": analysis_id,
            "clause_id": clause.get("clause_id", ""),
            "redis_client": redis_client,
            "on_thinking": on_thinking,
            "prior_verdict": prior_verdict,
        }
    }
    final_state: ClauseState = await _clause_graph.ainvoke(
        {"clause": clause},
        config=config,
    )
    return final_state.get("gap_result", dict(_INSUFFICIENT))

