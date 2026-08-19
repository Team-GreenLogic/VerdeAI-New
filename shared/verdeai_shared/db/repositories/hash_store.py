"""Hash store repository — SHA-256, pHash, FastCDC dedup records."""

from datetime import datetime, timezone
from typing import Any

from verdeai_shared.db.repositories.base import BaseRepository


class HashStoreRepository(BaseRepository):
    collection_name = "hash_store"

    def __init__(self, db: Any, tenant_id: str, profile_id: str) -> None:
        super().__init__(db, tenant_id)
        self._profile_id = profile_id

    def _filter(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        base: dict[str, Any] = {"tenant_id": self._tenant_id, "profile_id": self._profile_id}
        if extra:
            base.update(extra)
        return base

    async def find_by_sha256(self, sha256: str) -> dict[str, Any] | None:
        return await self._col.find_one(self._filter({"sha256": sha256}))

    async def upsert(
        self,
        *,
        sha256: str,
        document_id: str,
        phashes: list[str] | None = None,
        fastcdc_chunks: list[str] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            self._filter({"sha256": sha256}),
            {
                "$set": {
                    "tenant_id": self._tenant_id,
                    "profile_id": self._profile_id,
                    "sha256": sha256,
                    "document_id": document_id,
                    "phashes": phashes or [],
                    "fastcdc_chunks": fastcdc_chunks or [],
                    "created_at": now,
                }
            },
            upsert=True,
        )

    async def delete_by_document(self, document_id: str) -> None:
        await self._col.delete_one(self._filter({"document_id": document_id}))

    async def get_fastcdc_chunks(self, sha256: str) -> list[str]:
        doc = await self._col.find_one(
            self._filter({"sha256": sha256}),
            projection={"fastcdc_chunks": 1},
        )
        if doc is None:
            return []
        return doc.get("fastcdc_chunks", [])  # type: ignore[return-value]

