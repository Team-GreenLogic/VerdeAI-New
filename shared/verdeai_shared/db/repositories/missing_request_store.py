"""Missing request store repository."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class MissingRequestStoreRepository(BaseRepository):
    collection_name = "missing_request_store"

    async def insert_many(self, analysis_id: str, items: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc)
        docs = [
            {**i, "tenant_id": self._tenant_id, "analysis_id": analysis_id, "created_at": now}
            for i in items
        ]
        if docs:
            await self._col.insert_many(docs)

    async def list_for_analysis(self, analysis_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find(self._filter({"analysis_id": analysis_id}))
        return await cursor.to_list(length=None)
