"""Stage 4 — Image / diagram summaries via vision model.

For each image in the LlamaParse result, downloads the presigned URL,
encodes to base64, calls the vision model, and inserts an image_summary chunk.
"""

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from jinja2 import Environment, FileSystemLoader
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # type: ignore[import-untyped]

import bson

from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.chunks import ChunksRepository
from verdeai_shared.llm.openrouter_client import complete
from verdeai_shared.settings import settings

from app.progress import emit

import verdeai_shared as _vs_pkg
_PROMPTS_DIR = Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def run(tenant_id: str, document_id: str) -> int:
    """Summarise images and insert as image_summary chunks. Returns count."""
    db = get_database()

    doc = await db.documents.find_one(
        {"_id": bson.ObjectId(document_id), "tenant_id": tenant_id}
    )
    if doc is None or not doc.get("has_images"):
        return 0  # no images to process

    parsed_blob_ref = doc.get("parsed_blob_ref")
    if not parsed_blob_ref:
        return 0

    bucket = AsyncIOMotorGridFSBucket(db)
    buf = BytesIO()
    await bucket.download_to_stream(bson.ObjectId(parsed_blob_ref), buf)
    parsed: dict[str, Any] = json.loads(buf.getvalue())

    images: list[dict[str, Any]] = parsed.get("images", [])
    if not images:
        return 0

    await emit(tenant_id, document_id, "images", "running",
               f"Summarising {len(images)} images")

    tmpl = _jinja.get_template("image_summary.j2")
    chunks_repo = ChunksRepository(db, tenant_id)
    image_chunks: list[dict[str, Any]] = []

    for img in images:
        url: str = img.get("url") or img.get("presigned_url") or ""
        if not url:
            continue
        try:
            summary = await _summarise_image(tmpl, url)
            if summary:
                image_chunks.append({
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "text": summary,
                    "context_preamble": "",
                    "content_type": "image_summary",
                    "page": img.get("page_number", 1),
                    "embedding": [],
                    "image_metadata": {k: v for k, v in img.items() if k != "url"},
                })
        except Exception as exc:
            logger.warning("Image summary failed", url=url[:80], error=str(exc))

    if image_chunks:
        await chunks_repo.insert_many(image_chunks)

    await emit(tenant_id, document_id, "images", "done",
               f"{len(image_chunks)} image summaries created")
    return len(image_chunks)


async def _summarise_image(tmpl: Any, url: str) -> str:
    """Download image, encode base64, call vision model."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        image_data = base64.b64encode(resp.content).decode()
        mime = resp.headers.get("content-type", "image/png").split(";")[0]

    prompt_text = tmpl.render()
    response = await complete(
        model=settings.VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_data}"},
                    },
                ],
            }
        ],
        max_tokens=200,
        temperature=0.0,
    )
    return response.choices[0].message.content.strip()
