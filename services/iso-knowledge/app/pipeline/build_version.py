"""ISO version build pipeline — LangGraph StateGraph.

Converts uploaded PDF/DOCX files into structured ISO clauses + state template.

Pipeline stages:
  parse → detect_structure → extract_clauses → verify_coverage
                                    ↑                  |
                                    └── (missing) ─────┘  (max 2 re-extract loops)
                                 (complete) → gen_state_template → persist → END
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, TypedDict

import verdeai_shared as _vs_pkg
from bson import ObjectId
from jinja2 import Environment, FileSystemLoader
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # type: ignore[import-untyped]

from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_state import ISOStateRepository
from verdeai_shared.db.repositories.iso_versions import ISOVersionsRepository
from verdeai_shared.llm.openrouter_client import complete
from verdeai_shared.retrieval.embedder import embed_documents
from verdeai_shared.settings import settings

_PROMPTS_DIR = Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_MAX_VERIFY_ATTEMPTS = 2
_EXTRACT_CONCURRENCY = 4  # parallel clause extractions per batch

# ISO management-system standards (14001, 9001, 45001, ...) share the fixed
# "Harmonized Structure": clauses 1-3 (Scope, Normative references, Terms and
# definitions) are always non-normative front matter with no "shall" requirements
# to gap-check against. The LLM is asked to skip them but doesn't reliably comply
# run-to-run, so it's enforced deterministically here instead of trusting the model.
_NON_NORMATIVE_TOP_SECTIONS = {"0", "1", "2", "3"}


def _is_normative(clause_id: str) -> bool:
    top = clause_id.split(".", 1)[0].strip()
    return top not in _NON_NORMATIVE_TOP_SECTIONS


class BuildPaused(Exception):
    """Raised when the pipeline detects a pause signal and exits cleanly."""

# State template fields (same as default version for parity)
_STATE_FIELDS = [
    {"suffix": "gap_identified", "label": "Gap identified", "field_type": "boolean", "default": False},
    {"suffix": "conformance_score", "label": "Conformance score (0–1)", "field_type": "float", "default": 0.0},
    {"suffix": "evidence_notes", "label": "Evidence notes", "field_type": "string", "default": ""},
]

# Max chars to send to LLM (GPT-4 context ~120k tokens ≈ 480k chars; be conservative)
_MAX_DOC_CHARS = 180_000


class BuildState(TypedDict, total=False):
    version_id: str
    build_job_id: str
    tenant_id: str
    source_docs: list[dict[str, str]]  # [{gridfs_id, filename}]
    raw_markdown: str
    outline: list[dict[str, Any]]  # [{clause_id, section, title}]
    extracted: dict[str, dict[str, Any]]  # clause_id -> full clause doc
    missing_ids: list[str]
    attempts: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable") or {}


async def _emit_progress(
    tenant_id: str,
    build_job_id: str,
    stage: str,
    detail: str,
    redis_client: Any = None,
) -> None:
    """Emit a glassbox progress event for the admin UI build panel."""
    import redis.asyncio as aioredis
    import json as _json

    payload = json.dumps({"stage": stage, "status": "progress", "detail": detail})
    channel = f"glassbox.{tenant_id}.{build_job_id}"
    hist_key = f"glassbox_hist.{tenant_id}.{build_job_id}"

    own = redis_client is None
    r: aioredis.Redis = redis_client if redis_client is not None else aioredis.from_url(settings.REDIS_URL)  # type: ignore[type-arg]
    try:
        await r.publish(channel, payload)
        await r.rpush(hist_key, payload)
        await r.expire(hist_key, 7200)
    finally:
        if own:
            await r.aclose()


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def _pause_key(build_job_id: str) -> str:
    return f"iso_build_pause.{build_job_id}"


async def _check_paused(redis_client: Any, build_job_id: str) -> bool:
    import redis.asyncio as aioredis
    r: aioredis.Redis = redis_client  # type: ignore[type-arg]
    val = await r.get(_pause_key(build_job_id))
    return bool(val)


async def _parse_node(state: BuildState, config: RunnableConfig) -> dict[str, Any]:
    """Download all source docs from GridFS and parse via LlamaParse. Skipped on resume if checkpoint exists."""
    cfg = _cfg(config)
    db = cfg["db"]
    version_id: str = state["version_id"]
    build_job_id: str = state["build_job_id"]
    tenant_id: str = state["tenant_id"]
    source_docs: list[dict[str, str]] = state["source_docs"]
    redis_client = cfg.get("redis_client")

    # Resume: load checkpoint — skip expensive LlamaParse if already done
    checkpoint = await ISOVersionsRepository(db).get_build_checkpoint(version_id)
    if checkpoint and checkpoint.get("raw_markdown"):
        await _emit_progress(tenant_id, build_job_id, "parse", "Resuming from checkpoint — skipping parse", redis_client)
        return {
            "raw_markdown": checkpoint["raw_markdown"],
            "outline": checkpoint.get("outline", []),
            "extracted": checkpoint.get("extracted", {}),
            "attempts": 0,
            "missing_ids": [],
        }

    await _emit_progress(tenant_id, build_job_id, "parse", f"Parsing {len(source_docs)} document(s)", redis_client)

    bucket = AsyncIOMotorGridFSBucket(db)
    all_markdown: list[str] = []

    for doc_ref in source_docs:
        gridfs_id = doc_ref["gridfs_id"]
        filename = doc_ref.get("filename", "document.pdf")

        buf = BytesIO()
        try:
            await bucket.download_to_stream(ObjectId(gridfs_id), buf)
        except Exception as exc:
            logger.warning("Failed to download source doc from GridFS", gridfs_id=gridfs_id, error=str(exc))
            continue

        raw_bytes = buf.getvalue()
        suffix = Path(filename).suffix or ".pdf"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)

        try:
            await _emit_progress(tenant_id, build_job_id, "parse", f"Parsing {filename} via LlamaParse", redis_client)
            markdown = await _llamaparse_markdown(tmp_path, filename)
            all_markdown.append(f"# Document: {filename}\n\n{markdown}")
            logger.info("Parsed source doc", filename=filename, chars=len(markdown))
        except Exception as exc:
            logger.error("LlamaParse failed for doc", filename=filename, error=str(exc))
            raise
        finally:
            tmp_path.unlink(missing_ok=True)

    combined = "\n\n---\n\n".join(all_markdown)
    await _emit_progress(tenant_id, build_job_id, "parse", f"Parsed {len(source_docs)} doc(s), {len(combined):,} chars", redis_client)
    return {"raw_markdown": combined}


async def _llamaparse_markdown(path: Path, filename: str) -> str:
    from llama_cloud import AsyncLlamaCloud  # type: ignore[import-untyped]

    client = AsyncLlamaCloud(api_key=settings.LLAMA_CLOUD_API_KEY)
    file_obj = await client.files.create(file=str(path), purpose="parse")
    result = await client.parsing.parse(
        file_id=file_obj.id,
        tier=settings.LLAMA_PARSE_TIER,
        version="latest",
        expand=["markdown_full"],
    )
    return result.markdown_full or ""


async def _detect_structure_node(state: BuildState, config: RunnableConfig) -> dict[str, Any]:
    """Ask the LLM to extract the clause outline. Skipped on resume if outline already in state."""
    cfg = _cfg(config)
    version_id: str = state["version_id"]
    build_job_id: str = state["build_job_id"]
    tenant_id: str = state["tenant_id"]
    redis_client = cfg.get("redis_client")

    # Resume: outline already loaded from checkpoint in _parse_node
    if state.get("outline"):
        await _emit_progress(tenant_id, build_job_id, "structure", f"Resuming — outline already has {len(state['outline'])} clauses", redis_client)
        return {}

    await _emit_progress(tenant_id, build_job_id, "structure", "Detecting clause structure", redis_client)

    raw = state.get("raw_markdown", "")
    # Truncate if very large — send beginning and end to capture structure
    if len(raw) > _MAX_DOC_CHARS:
        half = _MAX_DOC_CHARS // 2
        doc_text = raw[:half] + "\n\n[... document truncated for structure detection ...]\n\n" + raw[-half:]
    else:
        doc_text = raw

    tmpl = _jinja.get_template("iso_detect_structure.j2")
    prompt = tmpl.render(document_text=doc_text)

    resp = await complete(
        model=settings.CHEAP_REASONING_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=4096,
        temperature=0.0,
        name="iso_detect_structure",
    )
    content = resp.choices[0].message.content or "{}"
    parsed = json.loads(content)
    raw_outline: list[dict[str, Any]] = parsed.get("clauses", [])

    # Deterministically drop non-normative front matter (Scope, Normative
    # references, Terms and definitions) regardless of what the LLM returned —
    # see _NON_NORMATIVE_TOP_SECTIONS.
    outline = [c for c in raw_outline if _is_normative(str(c.get("clause_id", "")))]
    dropped = len(raw_outline) - len(outline)
    if dropped:
        logger.info("Dropped non-normative clauses from outline", version_id=version_id, dropped=dropped)

    await _emit_progress(tenant_id, build_job_id, "structure", f"Found {len(outline)} clauses in outline", redis_client)
    logger.info("Clause outline detected", version_id=version_id, count=len(outline))
    return {"outline": outline, "extracted": {}, "attempts": 0, "missing_ids": []}


async def _extract_clauses_node(state: BuildState, config: RunnableConfig) -> dict[str, Any]:
    """Extract requirements per clause in batches, checking for pause between each batch."""
    cfg = _cfg(config)
    db = cfg["db"]
    version_id: str = state["version_id"]
    build_job_id: str = state["build_job_id"]
    tenant_id: str = state["tenant_id"]
    redis_client = cfg.get("redis_client")
    raw = state.get("raw_markdown", "")
    outline: list[dict[str, Any]] = state.get("outline", [])
    extracted: dict[str, dict[str, Any]] = dict(state.get("extracted", {}))
    missing_ids: list[str] = state.get("missing_ids", [])
    attempts: int = state.get("attempts", 0)

    # On retry only extract missing; on first pass extract all that aren't already done
    if missing_ids:
        to_extract = [c for c in outline if c["clause_id"] in missing_ids]
    else:
        to_extract = [c for c in outline if c["clause_id"] not in extracted]

    await _emit_progress(
        tenant_id, build_job_id, "extract",
        f"Extracting {len(to_extract)} clause(s) — {len(extracted)} already done (attempt {attempts + 1})",
        redis_client,
    )

    doc_text = raw[:_MAX_DOC_CHARS] if len(raw) > _MAX_DOC_CHARS else raw
    tmpl = _jinja.get_template("iso_extract_clause.j2")

    async def extract_one(clause: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        prompt = tmpl.render(
            clause_id=clause["clause_id"],
            section=clause["section"],
            title=clause["title"],
            document_text=doc_text,
        )
        try:
            resp = await complete(
                model=settings.CHEAP_REASONING_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=2560,
                temperature=0.0,
                name="iso_extract_clause",
            )
            content = resp.choices[0].message.content or "{}"
            result = json.loads(content)
        except Exception as exc:
            logger.warning("Clause extraction failed", clause_id=clause["clause_id"], error=str(exc))
            result = {
                "clause_id": clause["clause_id"],
                "section": clause["section"],
                "title": clause["title"],
                "requirements": "",
                "keywords": [],
                "search_query": "",
            }
        return clause["clause_id"], result

    # Process in batches of _EXTRACT_CONCURRENCY, checking for pause between each batch
    for batch_start in range(0, len(to_extract), _EXTRACT_CONCURRENCY):
        # Pause check before every batch
        if redis_client and await _check_paused(redis_client, build_job_id):
            logger.info("Build pause signal detected — saving checkpoint", version_id=version_id)
            await _emit_progress(
                tenant_id, build_job_id, "extract",
                f"Pausing — {len(extracted)}/{len(outline)} clauses extracted so far", redis_client,
            )
            await ISOVersionsRepository(db).save_build_checkpoint(
                version_id,
                raw_markdown=raw,
                outline=outline,
                extracted=extracted,
            )
            raise BuildPaused()

        batch = to_extract[batch_start: batch_start + _EXTRACT_CONCURRENCY]
        results = await asyncio.gather(*[extract_one(c) for c in batch])
        for clause_id, result in results:
            extracted[clause_id] = result
            await _emit_progress(tenant_id, build_job_id, "extract", f"Extracted clause {clause_id}", redis_client)

    return {"extracted": extracted, "attempts": attempts + 1}


async def _verify_coverage_node(state: BuildState, config: RunnableConfig) -> dict[str, Any]:
    """Check nothing was missed; return list of missing clause IDs."""
    cfg = _cfg(config)
    version_id: str = state["version_id"]
    build_job_id: str = state["build_job_id"]
    tenant_id: str = state["tenant_id"]
    redis_client = cfg.get("redis_client")
    outline: list[dict[str, Any]] = state.get("outline", [])
    extracted: dict[str, dict[str, Any]] = state.get("extracted", {})

    await _emit_progress(tenant_id, build_job_id, "verify", "Verifying coverage — checking nothing was dropped", redis_client)

    outline_ids = [c["clause_id"] for c in outline]
    extracted_ids = [cid for cid, data in extracted.items() if len(data.get("requirements", "")) >= 50]

    tmpl = _jinja.get_template("iso_verify_coverage.j2")
    prompt = tmpl.render(
        outline_json=json.dumps(outline_ids),
        extracted_ids_json=json.dumps(extracted_ids),
    )

    try:
        resp = await complete(
            model=settings.CHEAP_REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=512,
            temperature=0.0,
            name="iso_verify_coverage",
        )
        content = resp.choices[0].message.content or "{}"
        result = json.loads(content)
        missing_ids: list[str] = result.get("missing_ids", [])
    except Exception as exc:
        logger.warning("Coverage verification failed — assuming complete", error=str(exc))
        missing_ids = []

    if missing_ids:
        await _emit_progress(tenant_id, build_job_id, "verify", f"Found {len(missing_ids)} missing clause(s): {missing_ids}", redis_client)
    else:
        await _emit_progress(tenant_id, build_job_id, "verify", "All clauses verified — coverage complete", redis_client)

    return {"missing_ids": missing_ids}


def _route_after_verify(state: BuildState) -> str:
    missing = state.get("missing_ids", [])
    attempts = state.get("attempts", 0)
    if missing and attempts < _MAX_VERIFY_ATTEMPTS:
        return "extract_clauses"
    return "gen_state_template"


async def _gen_state_template_node(state: BuildState, config: RunnableConfig) -> dict[str, Any]:
    """No-op node — state template is generated during persist using standard fields."""
    cfg = _cfg(config)
    version_id: str = state["version_id"]
    build_job_id: str = state["build_job_id"]
    tenant_id: str = state["tenant_id"]
    redis_client = cfg.get("redis_client")
    count = len(state.get("extracted", {}))
    await _emit_progress(tenant_id, build_job_id, "template", f"Generating state template for {count} clauses", redis_client)
    return {}


async def _persist_node(state: BuildState, config: RunnableConfig) -> dict[str, Any]:
    """Embed all clauses and upsert into iso_clauses + iso_state_template."""
    cfg = _cfg(config)
    db = cfg["db"]
    version_id: str = state["version_id"]
    build_job_id: str = state["build_job_id"]
    tenant_id: str = state["tenant_id"]
    redis_client = cfg.get("redis_client")
    extracted: dict[str, dict[str, Any]] = state.get("extracted", {})
    outline: list[dict[str, Any]] = state.get("outline", [])

    # Preserve clause order from outline
    ordered_ids = [c["clause_id"] for c in outline]
    clauses = [extracted[cid] for cid in ordered_ids if cid in extracted]
    # Append any extracted clauses not in outline (shouldn't happen, but be safe)
    in_outline = set(ordered_ids)
    clauses += [v for k, v in extracted.items() if k not in in_outline]

    # Drop clauses with no usable requirements text — nothing to gap-check a
    # tenant's documents against, so persisting them is pure noise. Threshold
    # matches the one used in _verify_coverage_node.
    before = len(clauses)
    clauses = [c for c in clauses if len(c.get("requirements", "")) >= 50]
    if before != len(clauses):
        logger.info(
            "Dropped clauses with no extractable requirements",
            version_id=version_id, dropped=before - len(clauses),
        )

    await _emit_progress(tenant_id, build_job_id, "persist", f"Embedding {len(clauses)} clauses", redis_client)

    texts = [f"{c.get('title', '')}\n{c.get('requirements', '')}" for c in clauses]
    embeddings = await embed_documents(texts)

    iso_repo = ISOClausesRepository(db)
    state_repo = ISOStateRepository(db)
    versions_repo = ISOVersionsRepository(db)

    for clause, emb in zip(clauses, embeddings):
        doc: dict[str, Any] = {
            "version_id": version_id,
            "clause_id": clause.get("clause_id", ""),
            "section": clause.get("section", 0),
            "title": clause.get("title", ""),
            "requirements": clause.get("requirements", ""),
            "keywords": clause.get("keywords", []),
            "search_query": clause.get("search_query", ""),
            "embedding": emb,
        }
        await iso_repo.upsert(doc)

        # State template — 3 standard fields per clause
        cid = clause.get("clause_id", "")
        for field in _STATE_FIELDS:
            await state_repo.upsert({
                "version_id": version_id,
                "clause_id": cid,
                "field_path": f"{cid}.{field['suffix']}",
                "label": field["label"],
                "field_type": field["field_type"],
                "default": field["default"],
            })

    await versions_repo.set_clause_count(version_id, len(clauses))
    await versions_repo.update_status(version_id, "draft")
    await versions_repo.clear_build_checkpoint(version_id)

    done_payload = json.dumps({"stage": "complete", "status": "done", "detail": f"Build complete — {len(clauses)} clauses extracted as draft", "clause_count": len(clauses)})
    import redis.asyncio as aioredis
    channel = f"glassbox.{tenant_id}.{build_job_id}"
    hist_key = f"glassbox_hist.{tenant_id}.{build_job_id}"
    own = redis_client is None
    r: aioredis.Redis = redis_client if redis_client is not None else aioredis.from_url(settings.REDIS_URL)  # type: ignore[type-arg]
    try:
        await r.publish(channel, done_payload)
        await r.rpush(hist_key, done_payload)
        await r.expire(hist_key, 7200)
    finally:
        if own:
            await r.aclose()

    logger.info("ISO version build persisted", version_id=version_id, clauses=len(clauses))
    return {}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_graph() -> Any:
    g: StateGraph = StateGraph(BuildState)

    g.add_node("parse", _parse_node)
    g.add_node("detect_structure", _detect_structure_node)
    g.add_node("extract_clauses", _extract_clauses_node)
    g.add_node("verify_coverage", _verify_coverage_node)
    g.add_node("gen_state_template", _gen_state_template_node)
    g.add_node("persist", _persist_node)

    g.set_entry_point("parse")
    g.add_edge("parse", "detect_structure")
    g.add_edge("detect_structure", "extract_clauses")
    g.add_edge("extract_clauses", "verify_coverage")
    g.add_conditional_edges(
        "verify_coverage",
        _route_after_verify,
        {"extract_clauses": "extract_clauses", "gen_state_template": "gen_state_template"},
    )
    g.add_edge("gen_state_template", "persist")
    g.add_edge("persist", END)

    return g.compile()


_build_graph_instance = _build_graph()


async def build_version(
    db: Any,
    version_id: str,
    build_job_id: str,
    tenant_id: str,
    source_docs: list[dict[str, str]],
    redis_client: Any = None,
) -> None:
    """Invoke the LangGraph ISO version build pipeline."""
    from langchain_core.runnables import RunnableConfig

    config: RunnableConfig = {
        "configurable": {
            "db": db,
            "redis_client": redis_client,
        }
    }
    initial: BuildState = {
        "version_id": version_id,
        "build_job_id": build_job_id,
        "tenant_id": tenant_id,
        "source_docs": source_docs,
    }
    await _build_graph_instance.ainvoke(initial, config=config)
