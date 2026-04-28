"""Base repository that injects tenant_id into every query."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase  # type: ignore[import-untyped]


class BaseRepository:
    """All repositories inherit from this. tenant_id is injected on every query."""

    collection_name: str = ""

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str) -> None:  # type: ignore[type-arg]
        if not tenant_id:
            raise ValueError("tenant_id must be non-empty — repository cannot be constructed")
        self._db = db
        self._tenant_id = tenant_id
        self._col: AsyncIOMotorCollection = db[self.collection_name]  # type: ignore[type-arg]

    def _filter(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a query dict with tenant_id always included."""
        base: dict[str, Any] = {"tenant_id": self._tenant_id}
        if extra:
            base.update(extra)
        return base
