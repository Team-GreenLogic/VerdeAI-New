"""Org profile repository — per-tenant, per-version field values."""

from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID


class OrgProfileRepository(BaseRepository):
    collection_name = "org_profile"

    def __init__(self, db: Any, tenant_id: str, version_id: str = DEFAULT_VERSION_ID) -> None:
        super().__init__(db, tenant_id)
        self._version_id = version_id

    def _filter(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        base: dict[str, Any] = {"tenant_id": self._tenant_id, "version_id": self._version_id}
        if extra:
            base.update(extra)
        return base

    async def get(self, field_path: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({"field_path": field_path}))

    async def list_all(self) -> list[dict[str, Any]]:
        cursor = self._col.find(self._filter())
        return await cursor.to_list(length=None)

    async def list_for_clause(self, clause_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find(
            self._filter({"field_path": {"$regex": f"^{clause_id}\\."}}),
        )
        return await cursor.to_list(length=None)

    async def upsert(self, field_path: str, value: Any) -> None:
        await self._col.update_one(
            self._filter({"field_path": field_path}),
            {"$set": {"value": value}},
            upsert=True,
        )

    async def upsert_many(self, fields: dict[str, Any]) -> None:
        for field_path, value in fields.items():
            await self.upsert(field_path, value)
