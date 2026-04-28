"""Chunks repository."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class ChunksRepository(BaseRepository):
    collection_name = "chunks"

    async def insert_many(self, chunks: list[dict[str, Any]]) -> list[str]:
        now = datetime.now(timezone.utc)
        for chunk in chunks:
            chunk.setdefault("tenant_id", self._tenant_id)
            chunk.setdefault("created_at", now)
        result = await self._col.insert_many(chunks)
        return [str(oid) for oid in result.inserted_ids]

    async def find_by_document(self, document_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find(self._filter({"document_id": document_id}))
        return await cursor.to_list(length=None)

    async def delete_by_document(self, document_id: str) -> int:
        result = await self._col.delete_many(self._filter({"document_id": document_id}))
        return result.deleted_count
