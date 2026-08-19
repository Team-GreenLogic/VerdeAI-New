"""Result store repository — gap analysis results."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository
from verdeai_shared.iso.clause_order import clause_sort_key


class ResultStoreRepository(BaseRepository):
    collection_name = "result_store"

    async def upsert(self, analysis_id: str, clause_id: str, data: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            self._filter({"analysis_id": analysis_id, "clause_id": clause_id}),
            {
                "$set": {
                    **data,
                    "tenant_id": self._tenant_id,
                    "analysis_id": analysis_id,
                    "clause_id": clause_id,
                    "created_at": now,
                }
            },
            upsert=True,
        )

    async def list_for_analysis(self, analysis_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find(self._filter({"analysis_id": analysis_id}))
        results = await cursor.to_list(length=None)
        return sorted(results, key=lambda result: clause_sort_key(result.get("clause_id")))
