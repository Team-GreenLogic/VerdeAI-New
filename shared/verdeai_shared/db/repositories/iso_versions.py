"""ISO versions repository (global collection — no tenant filter)."""

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]

DEFAULT_VERSION_ID = "iso-14001-2015"


class ISOVersionsRepository:
    """Manages the global iso_versions catalog."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._col = db["iso_versions"]

    async def create(self, doc: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        doc.setdefault("status", "draft")
        doc.setdefault("clause_count", 0)
        doc.setdefault("source_docs", [])
        doc.setdefault("build_job_id", None)
        doc.setdefault("created_at", now)
        doc.setdefault("updated_at", now)
        doc.setdefault("published_at", None)
        await self._col.insert_one(doc)

    async def upsert(self, doc: dict[str, Any]) -> None:
        """Idempotent upsert keyed by version_id."""
        version_id = doc["version_id"]
        now = datetime.now(timezone.utc)
        doc["updated_at"] = now
        await self._col.update_one(
            {"version_id": version_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    async def get(self, version_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"version_id": version_id})

    async def list_all(self) -> list[dict[str, Any]]:
        cursor = self._col.find({}, sort=[("created_at", -1)])
        return await cursor.to_list(length=None)

    async def list_published(self) -> list[dict[str, Any]]:
        cursor = self._col.find({"status": "published"}, sort=[("published_at", -1)])
        return await cursor.to_list(length=None)

    async def update_status(
        self,
        version_id: str,
        status: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        update: dict[str, Any] = {"status": status, "updated_at": now}
        if status == "published":
            update["published_at"] = now
        if extra:
            update.update(extra)
        await self._col.update_one({"version_id": version_id}, {"$set": update})

    async def set_clause_count(self, version_id: str, count: int) -> None:
        await self._col.update_one(
            {"version_id": version_id},
            {"$set": {"clause_count": count, "updated_at": datetime.now(timezone.utc)}},
        )

    async def append_source_doc(self, version_id: str, gridfs_id: str, filename: str) -> None:
        await self._col.update_one(
            {"version_id": version_id},
            {
                "$push": {"source_docs": {"gridfs_id": gridfs_id, "filename": filename}},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def set_build_job(self, version_id: str, build_job_id: str) -> None:
        await self._col.update_one(
            {"version_id": version_id},
            {"$set": {"build_job_id": build_job_id, "updated_at": datetime.now(timezone.utc)}},
        )

    async def set_build_status(self, version_id: str, build_status: str) -> None:
        await self._col.update_one(
            {"version_id": version_id},
            {"$set": {"build_status": build_status, "updated_at": datetime.now(timezone.utc)}},
        )

    async def save_build_checkpoint(
        self,
        version_id: str,
        raw_markdown: str,
        outline: list[dict[str, Any]],
        extracted: dict[str, dict[str, Any]],
    ) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            {"version_id": version_id},
            {"$set": {
                "build_status": "paused",
                "build_checkpoint": {"raw_markdown": raw_markdown, "outline": outline, "extracted": extracted},
                "updated_at": now,
            }},
        )

    async def get_build_checkpoint(self, version_id: str) -> dict[str, Any] | None:
        doc = await self._col.find_one({"version_id": version_id}, {"build_checkpoint": 1})
        return doc.get("build_checkpoint") if doc else None

    async def clear_build_checkpoint(self, version_id: str) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            {"version_id": version_id},
            {"$unset": {"build_checkpoint": ""}, "$set": {"build_status": "building", "updated_at": now}},
        )

    async def delete(self, version_id: str) -> None:
        await self._col.delete_one({"version_id": version_id})

    async def count_analyses(self, db: AsyncIOMotorDatabase, version_id: str) -> int:  # type: ignore[type-arg]
        """Return how many analyses reference this version."""
        return await db["analyses"].count_documents({"version_id": version_id})
