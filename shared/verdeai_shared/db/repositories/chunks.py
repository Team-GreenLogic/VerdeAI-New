"""Chunks repository."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class ChunksRepository(BaseRepository):
    collection_name = "chunks"

    def __init__(self, db: Any, tenant_id: str, profile_id: str | None = None) -> None:
        super().__init__(db, tenant_id)
        self._profile_id = profile_id

    async def insert_many(self, chunks: list[dict[str, Any]]) -> list[str]:
        now = datetime.now(timezone.utc)
        for chunk in chunks:
            chunk.setdefault("tenant_id", self._tenant_id)
            chunk.setdefault("profile_id", self._profile_id)
            chunk.setdefault("created_at", now)
            # New chunks are live by default; supersession flips this when a modified
            # version of the document is uploaded (see supersede_document).
            chunk.setdefault("superseded", False)
        result = await self._col.insert_many(chunks)
        return [str(oid) for oid in result.inserted_ids]

    async def find_by_document(self, document_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find(self._filter({"document_id": document_id}))
        return await cursor.to_list(length=None)

    async def delete_by_document(self, document_id: str) -> int:
        result = await self._col.delete_many(self._filter({"document_id": document_id}))
        return result.deleted_count

    async def supersede_document(self, document_id: str, new_document_id: str) -> list[str]:
        """Soft-delete all live chunks of ``document_id`` because a modified version
        (``new_document_id``) has replaced it. Superseded chunks are excluded from
        retrieval but kept for audit/lineage. Returns the affected chunk ids so the
        caller can prune the BM25 index."""
        base = self._filter({"document_id": document_id, "superseded": {"$ne": True}})
        cursor = self._col.find(base, {"_id": 1})
        chunk_ids = [str(c["_id"]) async for c in cursor]
        if not chunk_ids:
            return []
        await self._col.update_many(
            base,
            {
                "$set": {
                    "superseded": True,
                    "superseded_at": datetime.now(timezone.utc),
                    "superseded_by_document_id": new_document_id,
                }
            },
        )
        return chunk_ids

