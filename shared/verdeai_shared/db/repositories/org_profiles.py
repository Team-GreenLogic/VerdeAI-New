"""Org profiles registry — one document per profile a tenant has created."""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from verdeai_shared.db.repositories.base import BaseRepository

_SUMMARY_FIELDS = ("org_name", "org_industry", "org_size", "org_location", "description")


class OrgProfilesRepository(BaseRepository):
    collection_name = "org_profiles"

    async def create(self, fields: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "tenant_id": self._tenant_id,
            "created_at": now,
            "updated_at": now,
            **{key: fields.get(key) for key in _SUMMARY_FIELDS},
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def get(self, profile_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(profile_id)
        except (InvalidId, TypeError):
            return None
        return await self._col.find_one(self._filter({"_id": oid}))

    async def list_all(self) -> list[dict[str, Any]]:
        cursor = self._col.find(self._filter(), sort=[("created_at", 1)])
        return await cursor.to_list(length=None)

    async def update(self, profile_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        updates = {key: value for key, value in fields.items() if key in _SUMMARY_FIELDS}
        updates["updated_at"] = datetime.now(timezone.utc)
        try:
            oid = ObjectId(profile_id)
        except (InvalidId, TypeError):
            return None
        await self._col.update_one(self._filter({"_id": oid}), {"$set": updates})
        return await self.get(profile_id)

    async def delete(self, profile_id: str) -> None:
        try:
            oid = ObjectId(profile_id)
        except (InvalidId, TypeError):
            return
        await self._col.delete_one(self._filter({"_id": oid}))

