"""ISO clauses repository (global collection — no tenant filter)."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]


class ISOClausesRepository:
    """ISO clauses are global (not per-tenant) — no BaseRepository."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db["iso_clauses"]

    async def upsert(self, clause: dict[str, Any]) -> None:
        await self._col.update_one(
            {"clause_id": clause["clause_id"]},
            {"$set": clause},
            upsert=True,
        )

    async def get(self, clause_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"clause_id": clause_id})

    async def list_all(self) -> list[dict[str, Any]]:
        cursor = self._col.find({})
        return await cursor.to_list(length=None)
