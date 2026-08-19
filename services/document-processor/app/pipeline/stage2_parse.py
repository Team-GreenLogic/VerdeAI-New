"""Stage 2 — Cloud parse with LlamaParse.

Uploads raw bytes to LlamaParse, retrieves:
  - markdown_full / text_full  — full document content
  - per-page markdown           — used to count pages
  - images_content_metadata     — presigned URLs for images (fed to Stage 4 vision model)

Stores the parsed result JSON in GridFS and updates the documents row
with parsed_blob_ref, pages, and has_images flag.
"""

import json
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # type: ignore[import-untyped]

from verdeai_shared.db.mongo import get_database
from verdeai_shared.settings import settings

from app.progress import emit


async def run(tenant_id: str, document_id: str) -> int:
    """Run LlamaParse stage. Returns number of pages parsed."""
    db = get_database()

    await emit(tenant_id, document_id, "parse", "running", "Uploading to LlamaParse")

    # --- Fetch raw bytes from GridFS ---
    import bson
    doc = await db.documents.find_one(
        {"_id": bson.ObjectId(document_id), "tenant_id": tenant_id}
    )
    if doc is None:
        raise RuntimeError(f"Document {document_id} not found")

    gridfs_id = doc.get("gridfs_id")
    if gridfs_id is None:
        raise RuntimeError(f"Document {document_id} has no gridfs_id")

    bucket = AsyncIOMotorGridFSBucket(db)
    buf = BytesIO()
    await bucket.download_to_stream(gridfs_id, buf)
    raw_bytes = buf.getvalue()

    filename: str = doc.get("filename", "document.pdf")

    # --- Write to temp file and parse via LlamaParse ---
    suffix = Path(filename).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = Path(tmp.name)

    try:
        await emit(tenant_id, document_id, "parse", "running", "Parsing document (LlamaParse)")
        parsed = await _llamaparse(tmp_path, filename)
    finally:
        tmp_path.unlink(missing_ok=True)

    pages: int = parsed["pages"]
    has_images: bool = len(parsed.get("images", [])) > 0

    logger.info(
        "LlamaParse complete",
        tenant_id=tenant_id,
        document_id=document_id,
        pages=pages,
        images=len(parsed.get("images", [])),
    )

    # --- Store result JSON in GridFS ---
    blob_bytes = json.dumps(parsed, default=str).encode("utf-8")
    blob_buf = BytesIO(blob_bytes)
    blob_id = await bucket.upload_from_stream(
        f"{document_id}_parsed.json",
        blob_buf,
        metadata={
            "tenant_id": tenant_id,
            "document_id": document_id,
            "type": "llamaparse_json",
        },
    )

    # --- Update documents row ---
    await db.documents.update_one(
        {"_id": bson.ObjectId(document_id)},
        {
            "$set": {
                "parsed_blob_ref": str(blob_id),
                "pages": pages,
                "has_images": has_images,
                "status": "parsed",
            }
        },
    )

    await emit(tenant_id, document_id, "parse", "done", f"Parsed {pages} pages")
    return pages


async def _llamaparse(path: Path, filename: str) -> dict[str, Any]:
    """Upload file to LlamaParse and return structured result."""
    from llama_cloud import AsyncLlamaCloud  # type: ignore[import-untyped]

    client = AsyncLlamaCloud(api_key=settings.LLAMA_CLOUD_API_KEY, base_url='https://api.cloud.llamaindex.ai')

    # Upload file — pass path string; SDK opens and streams the file
    file_obj = await client.files.create(
        file=str(path),
        purpose="parse",
    )

    # Parse with image metadata
    result = await client.parsing.parse(
        file_id=file_obj.id,
        tier=settings.LLAMA_PARSE_TIER,
        version="latest",
        expand=["markdown_full", "text_full", "images_content_metadata"],
    )

    # Page count: LlamaParse separates pages with horizontal rules in the markdown
    markdown_full: str = result.markdown_full or ""
    pages = max(1, markdown_full.count("\n---\n") + 1) if markdown_full else 0

    # Serialise image metadata
    images: list[dict[str, Any]] = []
    for img in result.images_content_metadata or []:
        if hasattr(img, "model_dump"):
            images.append(img.model_dump())
        elif isinstance(img, dict):
            images.append(img)
        else:
            images.append({"raw": str(img)})

    return {
        "markdown_full": result.markdown_full or "",
        "text_full": result.text_full or "",
        "pages": pages,
        "images": images,
        "file_id": file_obj.id,   # kept so Stage 4 can re-fetch images if URLs expired
    }

