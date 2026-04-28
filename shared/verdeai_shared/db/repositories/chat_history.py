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
