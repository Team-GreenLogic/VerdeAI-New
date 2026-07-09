"""ISO clauses repository (global collection — no tenant filter)."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]

from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID


class ISOClausesRepository:
    """ISO clauses are global (not per-tenant) — no BaseRepository."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db["iso_clauses"]

    async def upsert(self, clause: dict[str, Any]) -> None:
        clause.setdefault("version_id", DEFAULT_VERSION_ID)
        await self._col.update_one(
            {"version_id": clause["version_id"], "clause_id": clause["clause_id"]},
            {"$set": clause},
            upsert=True,
        )

    async def get(self, clause_id: str, version_id: str = DEFAULT_VERSION_ID) -> dict[str, Any] | None:
        return await self._col.find_one({"version_id": version_id, "clause_id": clause_id})

    async def list_all(self, version_id: str = DEFAULT_VERSION_ID) -> list[dict[str, Any]]:
        cursor = self._col.find({"version_id": version_id})
        return await cursor.to_list(length=None)

    async def delete_for_version(self, version_id: str) -> int:
        result = await self._col.delete_many({"version_id": version_id})
        return result.deleted_count

    async def count_for_version(self, version_id: str) -> int:
        return await self._col.count_documents({"version_id": version_id})
