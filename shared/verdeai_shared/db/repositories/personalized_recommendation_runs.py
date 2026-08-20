"""Tenant-scoped persistence for web-grounded recommendation runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class PersonalizedRecommendationRunsRepository(BaseRepository):
    collection_name = "personalized_recommendation_runs"

    async def create(self, doc: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        record = {
            **doc,
            "tenant_id": self._tenant_id,
            "active_profile_key": doc["profile_id"],
            "status": "queued",
            "sources": [],
            "recommendations": [],
            "warnings": [],
            "created_at": now,
            "updated_at": now,
        }
        await self._col.insert_one(record)
        return record

    async def get(self, run_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({"run_id": run_id}))

    async def list_for_profile(self, profile_id: str, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self._col.find(
            self._filter({"profile_id": profile_id}),
            sort=[("created_at", -1)],
            limit=limit,
        )
        return await cursor.to_list(length=None)

    async def find_active(self, profile_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({
            "profile_id": profile_id,
            "status": {"$in": ["queued", "researching", "synthesizing"]},
        }))

    async def update(self, run_id: str, **fields: Any) -> None:
        fields["updated_at"] = datetime.now(UTC)
        update: dict[str, Any] = {"$set": fields}
        if fields.get("status") in {"complete", "failed"}:
            update["$unset"] = {"active_profile_key": ""}
        await self._col.update_one(self._filter({"run_id": run_id}), update)
