"""Recommendation store repository."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class RecommendationStoreRepository(BaseRepository):
    collection_name = "recommendation_store"

    async def insert_many(self, analysis_id: str, recs: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc)
        docs = [
            {**r, "tenant_id": self._tenant_id, "analysis_id": analysis_id, "created_at": now}
            for r in recs
        ]
        if docs:
            await self._col.insert_many(docs)

    async def list_for_analysis(self, analysis_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find(self._filter({"analysis_id": analysis_id}))
        return await cursor.to_list(length=None)
