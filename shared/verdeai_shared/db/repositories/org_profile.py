"""Org profile repository — per-tenant field values."""

from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class OrgProfileRepository(BaseRepository):
    collection_name = "org_profile"

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
        """Bulk-upsert a mapping of field_path → value."""
        for field_path, value in fields.items():
            await self.upsert(field_path, value)
