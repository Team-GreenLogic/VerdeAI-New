"""State store repository — per-tenant per-clause evidence state."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class StateStoreRepository(BaseRepository):
    collection_name = "state_store"

    async def upsert(self, clause_id: str, data: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            self._filter({"clause_id": clause_id}),
            {"$set": {**data, "tenant_id": self._tenant_id, "updated_at": now}},
            upsert=True,
        )

    async def get(self, clause_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({"clause_id": clause_id}))
