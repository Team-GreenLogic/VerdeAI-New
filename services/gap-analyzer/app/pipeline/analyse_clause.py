"""Per-clause gap analysis pipeline — LangGraph StateGraph.

Each ISO clause is analysed through an 8-node graph:
  embed → retrieve → [conditional]
                       ├─ (chunks found) → load_org_profile → load_state_template
                       │                   → state_compare → gap_analyse → persist → END
                       └─ (no chunks)    → insufficient_persist → END

Each node emits a ``clause_stage`` progress event before executing,
giving the frontend step-by-step visibility within a clause.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypedDict

import verdeai_shared as _vs_pkg
from jinja2 import Environment, FileSystemLoader
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from loguru import logger

from verdeai_shared.db.repositories.iso_state import ISOStateRepository
from verdeai_shared.db.repositories.result_store import ResultStoreRepository
from verdeai_shared.llm.openrouter_client import stream_with_reasoning
from verdeai_shared.retrieval.embedder import embed_query
from verdeai_shared.retrieval.hybrid import hybrid_retrieve
from verdeai_shared.settings import settings

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
    ("embed",         "Embedding clause text\u2026"),
    ("retrieve",      "Retrieving relevant evidence\u2026"),
    ("load_profile",  "Loading organisation profile\u2026"),
    ("load_template", "Loading ISO state template\u2026"),
    ("state_compare", "Comparing state against evidence\u2026"),
    ("gap_analyse",   "Running gap analysis\u2026"),
    ("persist",       "Persisting result\u2026"),
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
    query_vector: list[float]
    chunks: list[dict[str, Any]]
    evidence_text: str
    org_profile_map: dict[str, Any]
    state_template_list: list[dict[str, Any]]
    state_diff: dict[str, Any]
    gap_result: dict[str, Any]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        page = c.get("page", "?")
        text = c.get("text", "")
        parts.append(f"[Chunk {i} | Page {page}]\n{text}")
    return "\n\n---\n\n".join(parts)


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

async def _embed_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("embed", config)
    clause = state["clause"]
    clause_id: str = clause["clause_id"]
    query_text = f"{clause.get('title', clause_id)}\n{clause.get('requirements', '')}"
    # Let exceptions propagate — the actor catches them and records a proper Error
    # decision rather than silently cascading Insufficient Evidence to all remaining clauses.
    vector: list[float] = await embed_query(query_text)
    return {"query_vector": vector}


async def _retrieve_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("retrieve", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause = state["clause"]
    clause_id: str = clause["clause_id"]
    query_text = f"{clause.get('title', clause_id)}\n{clause.get('requirements', '')}"
    # Let exceptions propagate so the actor can distinguish a retrieval failure
    # from a genuine "no documents in the knowledge base" result.
    chunks = await hybrid_retrieve(cfg["db"], cfg["tenant_id"], query_text, state["query_vector"])
    evidence_text = _format_chunks(chunks) if chunks else ""
    return {"chunks": chunks, "evidence_text": evidence_text}


async def _load_org_profile_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("load_profile", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause_id: str = state["clause"]["clause_id"]
    org_cursor = cfg["db"].org_profile.find(
        {"tenant_id": cfg["tenant_id"], "field_path": {"$regex": f"^{clause_id}\\."}}
    )
    org_entries = await org_cursor.to_list(None)
    return {"org_profile_map": {e["field_path"]: e.get("value") for e in org_entries}}


async def _load_state_template_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("load_template", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause_id: str = state["clause"]["clause_id"]
    state_entries = await ISOStateRepository(cfg["db"]).list_for_clause(clause_id)
    return {
        "state_template_list": [
            {
                "field_path": e["field_path"],
                "label": e.get("label"),
                "field_type": e.get("field_type"),
                "default": e.get("default"),
            }
            for e in state_entries
        ]
    }


async def _state_compare_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("state_compare", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause = state["clause"]
    clause_id: str = clause["clause_id"]
    clause_title: str = clause.get("title", clause_id)
    on_thinking: Callable[[str], Awaitable[None]] | None = cfg.get("on_thinking")
    state_diff: dict[str, Any] = {}
    try:
        system_prompt = _jinja.get_template("state_compare_system.j2").render()
        user_prompt = _jinja.get_template("state_compare_user.j2").render(
            clause_id=clause_id,
            clause_title=clause_title,
            clause_requirements=clause.get("requirements", ""),
            org_profile_json=json.dumps(state.get("org_profile_map", {}), indent=2),
            state_template_json=json.dumps(state.get("state_template_list", []), indent=2),
            evidence_chunks=state.get("evidence_text", ""),
        )
        answer = await stream_with_reasoning(
            model=settings.PRIMARY_REASONING_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=8192,
            temperature=0.0,
            response_format={"type": "json_object"},
            on_thinking=on_thinking,
            name="state_compare",
        )
        state_diff = json.loads(answer)
    except Exception as exc:
        logger.warning("state_compare LLM call failed", clause_id=clause_id, error=str(exc))
    return {"state_diff": state_diff}


async def _gap_analyse_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("gap_analyse", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause = state["clause"]
    clause_id: str = clause["clause_id"]
    clause_title: str = clause.get("title", clause_id)
    on_thinking: Callable[[str], Awaitable[None]] | None = cfg.get("on_thinking")

    # Pause check between the two LLM calls
    analysis_id: str = cfg["analysis_id"]
    status_doc = await cfg["db"].analyses.find_one({"analysis_id": analysis_id}, {"status": 1})
    if status_doc and status_doc.get("status") == "paused":
        raise AnalysisPaused(analysis_id)

    state_diff = state.get("state_diff", {})
    gap_result: dict[str, Any] = {}
    try:
        system_prompt = _jinja.get_template("gap_analyse_system.j2").render()
        user_prompt = _jinja.get_template("gap_analyse_user.j2").render(
            clause_id=clause_id,
            clause_title=clause_title,
            clause_requirements=clause.get("requirements", ""),
            state_diff_json=json.dumps(state_diff.get("state_diff", {}), indent=2),
            reference_context_json=json.dumps(state_diff.get("reference_context", {}), indent=2),
            evidence_chunks=state.get("evidence_text", ""),
        )
        answer = await stream_with_reasoning(
            model=settings.PRIMARY_REASONING_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=8192,
            temperature=0.0,
            response_format={"type": "json_object"},
            on_thinking=on_thinking,
            name="gap_analyse",
        )
        gap_result = json.loads(answer)
    except AnalysisPaused:
        raise
    except Exception as exc:
        logger.warning("gap_analyse LLM call failed", clause_id=clause_id, error=str(exc))
        gap_result = dict(_INSUFFICIENT)
        gap_result["reasoning"] = f"LLM call failed: {exc}"
    return {"gap_result": gap_result}


async def _persist_node(state: ClauseState, config: RunnableConfig) -> dict[str, Any]:
    await _emit_step("persist", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause_id: str = state["clause"]["clause_id"]
    gap_result = state.get("gap_result", dict(_INSUFFICIENT))
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
    """Shortcut path when no evidence chunks were retrieved — skip all LLM calls."""
    await _emit_step("persist", config)
    cfg: dict[str, Any] = config.get("configurable") or {}  # type: ignore[assignment]
    clause_id: str = state["clause"]["clause_id"]
    result = dict(_INSUFFICIENT)
    await ResultStoreRepository(cfg["db"], cfg["tenant_id"]).upsert(
        cfg["analysis_id"], clause_id, result
    )
    logger.info("No chunks retrieved — insufficient evidence", clause_id=clause_id)
    return {"gap_result": result}


# ── Conditional edge ──────────────────────────────────────────────────────────

def _route_after_retrieve(state: ClauseState) -> str:
    """Route to full pipeline if chunks found, else skip to insufficient evidence."""
    return "load_org_profile" if state.get("chunks") else "insufficient_persist"


# ── Graph construction ────────────────────────────────────────────────────────

def _build_clause_graph() -> Any:  # returns CompiledStateGraph
    g: StateGraph = StateGraph(ClauseState)  # type: ignore[type-arg]

    g.add_node("embed",                _embed_node)
    g.add_node("retrieve",             _retrieve_node)
    g.add_node("load_org_profile",     _load_org_profile_node)
    g.add_node("load_state_template",  _load_state_template_node)
    g.add_node("state_compare",        _state_compare_node)
    g.add_node("gap_analyse",          _gap_analyse_node)
    g.add_node("persist",              _persist_node)
    g.add_node("insufficient_persist", _insufficient_persist_node)

    g.set_entry_point("embed")
    g.add_edge("embed", "retrieve")

    # If retrieve returned chunks → full pipeline; else → skip LLM calls
    g.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {
            "load_org_profile":    "load_org_profile",
            "insufficient_persist": "insufficient_persist",
        },
    )

    g.add_edge("load_org_profile",    "load_state_template")
    g.add_edge("load_state_template", "state_compare")
    g.add_edge("state_compare",       "gap_analyse")
    g.add_edge("gap_analyse",         "persist")
    g.add_edge("persist",             END)
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
    analysis_id: str,
    clause: dict[str, Any],
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
    redis_client: Any = None,
) -> dict[str, Any]:
    """Invoke the LangGraph clause pipeline. Returns the gap result dict."""
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
            "analysis_id": analysis_id,
            "clause_id": clause.get("clause_id", ""),
            "redis_client": redis_client,
            "on_thinking": on_thinking,
        }
    }
    final_state: ClauseState = await _clause_graph.ainvoke(
        {"clause": clause},
        config=config,
    )
    return final_state.get("gap_result", dict(_INSUFFICIENT))
