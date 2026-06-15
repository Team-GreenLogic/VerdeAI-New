"""Stage 3 — Chunking + contextualisation.

Loads the LlamaParse markdown from GridFS, splits it into ≤512-token chunks,
generates a document-level summary (one LLM call, cached), then contextualises
each chunk with a 1-2 sentence preamble (one cheap LLM call per chunk).
"""

import json
from io import BytesIO
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # type: ignore[import-untyped]

from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.chunks import ChunksRepository
from verdeai_shared.llm.openrouter_client import complete
from verdeai_shared.settings import settings

from app.progress import emit

# Prompt templates
import verdeai_shared as _vs_pkg
_PROMPTS_DIR = Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_SUMMARY_SYSTEM = (
    "You are a document analyst. Summarise the following document in one sentence, "
    "focusing on its subject matter and purpose."
)
_CHUNK_TARGET_TOKENS = 512
_CHUNK_OVERLAP_TOKENS = 64


async def run(tenant_id: str, document_id: str) -> int:
    """Chunk and contextualise the parsed document. Returns number of chunks created."""
    import bson

    db = get_database()
    await emit(tenant_id, document_id, "chunk", "running", "Loading parsed content")

    # --- Load parsed JSON from GridFS ---
    doc = await db.documents.find_one(
        {"_id": bson.ObjectId(document_id), "tenant_id": tenant_id}
    )
    if doc is None:
        raise RuntimeError(f"Document {document_id} not found")

    parsed_blob_ref = doc.get("parsed_blob_ref")
    if not parsed_blob_ref:
        raise RuntimeError(f"Document {document_id} has no parsed_blob_ref")

    bucket = AsyncIOMotorGridFSBucket(db)
    buf = BytesIO()
    await bucket.download_to_stream(bson.ObjectId(parsed_blob_ref), buf)
    parsed: dict[str, Any] = json.loads(buf.getvalue())

    markdown_full: str = parsed.get("markdown_full", "") or parsed.get("text_full", "")
    if not markdown_full:
        logger.warning("No markdown content found", document_id=document_id)
        return 0

    # --- Document summary (one call, cached) ---
    summary: str = doc.get("summary", "")
    if not summary:
        summary = await _generate_summary(markdown_full)
        await db.documents.update_one(
            {"_id": bson.ObjectId(document_id)},
            {"$set": {"summary": summary}},
        )

    # --- Split into chunks ---
    raw_chunks = _split_markdown(markdown_full)
    logger.info(
        "Split into chunks",
        document_id=document_id,
        count=len(raw_chunks),
    )

    await emit(tenant_id, document_id, "chunk", "running",
               f"Contextualising {len(raw_chunks)} chunks")

    # --- Contextualise each chunk ---
    tmpl = _jinja.get_template("contextualise_chunk.j2")
    chunks_repo = ChunksRepository(db, tenant_id)
    chunk_docs: list[dict[str, Any]] = []

    for i, chunk_text in enumerate(raw_chunks):
        preamble = await _contextualise(tmpl, summary, chunk_text)
        full_text = f"CONTEXT: {preamble}\n\n{chunk_text}" if preamble else chunk_text
        chunk_docs.append({
            "tenant_id": tenant_id,
            "document_id": document_id,
            "chunk_index": i,
            "text": full_text,
            "context_preamble": preamble,
            "content_type": "text",
            "page": _estimate_page(i, len(raw_chunks), doc.get("pages", 1)),
            "embedding": [],   # filled by Stage 5
        })

    inserted_ids = await chunks_repo.insert_many(chunk_docs)
    logger.info(
        "Chunks inserted",
        tenant_id=tenant_id,
        document_id=document_id,
        count=len(inserted_ids),
    )
    await emit(tenant_id, document_id, "chunk", "done",
               f"{len(inserted_ids)} chunks created")
    return len(inserted_ids)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_markdown(text: str) -> list[str]:
    """Split markdown into ≤512-token chunks with overlap."""
    from langchain_text_splitters import MarkdownTextSplitter  # type: ignore[import-untyped]

    splitter = MarkdownTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=_CHUNK_TARGET_TOKENS,
        chunk_overlap=_CHUNK_OVERLAP_TOKENS,
    )
    docs = splitter.create_documents([text])
    return [d.page_content for d in docs if d.page_content.strip()]


async def _generate_summary(text: str) -> str:
    """Generate a one-sentence document summary."""
    # Feed only the first ~3000 chars to keep tokens low
    preview = text[:3000]
    try:
        resp = await complete(
            model=settings.CHEAP_REASONING_MODEL,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user", "content": preview},
            ],
            max_tokens=120,
            temperature=0.0,
            name="chunk_summary",
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Summary generation failed", error=str(exc))
        return ""


async def _contextualise(tmpl: Any, summary: str, chunk_text: str) -> str:
    """Generate a 1-2 sentence contextual preamble for a chunk."""
    prompt = tmpl.render(document_summary=summary, chunk_text=chunk_text[:1500])
    try:
        resp = await complete(
            model=settings.CHEAP_REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.0,
            name="contextualise_chunk",
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Contextualisation failed", error=str(exc))
        return ""


def _estimate_page(chunk_index: int, total_chunks: int, total_pages: int) -> int:
    """Estimate the page number for a chunk based on its position."""
    if total_chunks == 0 or total_pages == 0:
        return 1
    return max(1, round((chunk_index / total_chunks) * total_pages) + 1)
