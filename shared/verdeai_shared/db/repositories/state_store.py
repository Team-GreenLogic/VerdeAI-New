"""State store repository — per-tenant, per-version, per-clause evidence state."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID


class StateStoreRepository(BaseRepository):
    collection_name = "state_store"

    def __init__(self, db: Any, tenant_id: str, version_id: str = DEFAULT_VERSION_ID) -> None:
        super().__init__(db, tenant_id)
        self._version_id = version_id

    def _filter(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        base: dict[str, Any] = {"tenant_id": self._tenant_id, "version_id": self._version_id}
        if extra:
            base.update(extra)
        return base

    async def upsert(self, clause_id: str, data: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            self._filter({"clause_id": clause_id}),
            {"$set": {**data, "tenant_id": self._tenant_id, "version_id": self._version_id, "updated_at": now}},
            upsert=True,
        )

    async def get(self, clause_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({"clause_id": clause_id}))
