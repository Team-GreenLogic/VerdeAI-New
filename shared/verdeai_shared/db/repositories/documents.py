"""Documents repository."""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from verdeai_shared.db.repositories.base import BaseRepository


class DocumentsRepository(BaseRepository):
    collection_name = "documents"

    async def insert(
        self,
        *,
        filename: str,
        sha256: str,
        status: str = "queued",
    ) -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "tenant_id": self._tenant_id,
            "filename": filename,
            "sha256": sha256,
            "status": status,
            "pages": None,
            "docling_blob_ref": None,
            "summary": None,
            "created_at": now,
        }
        result = await self._col.insert_one(doc)
        return str(result.inserted_id)

    async def get(self, document_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({"_id": ObjectId(document_id)}))

    async def list_by_status(self, status: str | None = None) -> list[dict[str, Any]]:
        query = self._filter({"status": status} if status else None)
        cursor = self._col.find(query)
        return await cursor.to_list(length=None)

    async def update_status(self, document_id: str, status: str, **extra: Any) -> None:
        update: dict[str, Any] = {"status": status, **extra}
        await self._col.update_one(
            self._filter({"_id": ObjectId(document_id)}),
            {"$set": update},
        )

    async def find_by_sha256(self, sha256: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({"sha256": sha256}))

    async def delete(self, document_id: str) -> None:
        await self._col.update_one(
            self._filter({"_id": ObjectId(document_id)}),
            {"$set": {"status": "deleted"}},
        )
