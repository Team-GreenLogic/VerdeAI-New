"""ISO state template repository (global collection — no tenant filter)."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]


class ISOStateRepository:
    """ISO state template is global. Per-tenant values live in org_profile."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db["iso_state_template"]

    async def upsert(self, entry: dict[str, Any]) -> None:
        await self._col.update_one(
            {"field_path": entry["field_path"]},
            {"$set": entry},
            upsert=True,
        )

    async def list_for_clause(self, clause_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find({"clause_id": clause_id})
        return await cursor.to_list(length=None)

    async def list_all(self) -> list[dict[str, Any]]:
        cursor = self._col.find({})
        return await cursor.to_list(length=None)
