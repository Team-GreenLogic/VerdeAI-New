"""ISO state template repository (global collection — no tenant filter)."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]

from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID


class ISOStateRepository:
    """ISO state template is global. Per-tenant values live in org_profile."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db["iso_state_template"]

    async def upsert(self, entry: dict[str, Any]) -> None:
        entry.setdefault("version_id", DEFAULT_VERSION_ID)
        await self._col.update_one(
            {"version_id": entry["version_id"], "field_path": entry["field_path"]},
            {"$set": entry},
            upsert=True,
        )

    async def list_for_clause(
        self, clause_id: str, version_id: str = DEFAULT_VERSION_ID
    ) -> list[dict[str, Any]]:
        cursor = self._col.find({"version_id": version_id, "clause_id": clause_id})
        return await cursor.to_list(length=None)

    async def list_all(self, version_id: str = DEFAULT_VERSION_ID) -> list[dict[str, Any]]:
        cursor = self._col.find({"version_id": version_id})
        return await cursor.to_list(length=None)

    async def delete_for_version(self, version_id: str) -> int:
        result = await self._col.delete_many({"version_id": version_id})
        return result.deleted_count

    async def delete_for_clause(self, version_id: str, clause_id: str) -> int:
        result = await self._col.delete_many({"version_id": version_id, "clause_id": clause_id})
        return result.deleted_count
