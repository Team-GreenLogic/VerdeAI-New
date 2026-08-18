"""Chat history and memory summary repositories."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class ChatHistoryRepository(BaseRepository):
    collection_name = "chat_history"

    async def append(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "tenant_id": self._tenant_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "citations": citations or [],
            "created_at": now,
        }
        result = await self._col.insert_one(doc)
        return str(result.inserted_id)

    async def list_recent(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        cursor = self._col.find(
            self._filter({"session_id": session_id}),
            sort=[("created_at", -1)],
            limit=limit,
        )
        items = await cursor.to_list(length=None)
        return list(reversed(items))

    async def list_all(self, session_id: str) -> list[dict[str, Any]]:
        """Full chronological message list for one session (no cap)."""
        cursor = self._col.find(
            self._filter({"session_id": session_id}),
            sort=[("created_at", 1)],
        )
        return await cursor.to_list(length=None)

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        """One row per session for this tenant: title (first message), last activity, message count."""
        pipeline = [
            {"$match": self._filter()},
            {"$sort": {"created_at": 1}},
            {
                "$group": {
                    "_id": "$session_id",
                    "title": {"$first": "$content"},
                    "last_message_at": {"$last": "$created_at"},
                    "message_count": {"$sum": 1},
                }
            },
            {"$sort": {"last_message_at": -1}},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "session_id": "$_id",
                    "title": 1,
                    "last_message_at": 1,
                    "message_count": 1,
                }
            },
        ]
        return await self._col.aggregate(pipeline).to_list(length=None)

    async def delete_session(self, session_id: str) -> int:
        result = await self._col.delete_many(self._filter({"session_id": session_id}))
        return result.deleted_count


class ChatMemorySummaryRepository(BaseRepository):
    collection_name = "chat_memory_summary"

    async def upsert(self, session_id: str, summary: str) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            self._filter({"session_id": session_id}),
            {
                "$set": {
                    "tenant_id": self._tenant_id,
                    "session_id": session_id,
                    "summary": summary,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    async def get(self, session_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({"session_id": session_id}))
