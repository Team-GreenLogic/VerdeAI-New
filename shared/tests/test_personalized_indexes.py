"""Index migration contracts for personalized recommendation runs."""

from types import SimpleNamespace

import pytest
from verdeai_shared.db.indexes import (
    _ACTIVE_RECOMMENDATION_INDEX,
    _LEGACY_ACTIVE_RECOMMENDATION_INDEX,
    _ensure_personalized_recommendation_indexes,
)


class _FakeCollection:
    def __init__(self) -> None:
        self.dropped: list[str] = []
        self.created: list[object] = []

    async def index_information(self) -> dict[str, dict[str, object]]:
        return {
            _LEGACY_ACTIVE_RECOMMENDATION_INDEX: {
                "unique": True,
                "sparse": True,
            }
        }

    async def drop_index(self, name: str) -> None:
        self.dropped.append(name)

    async def create_indexes(self, indexes: list[object]) -> None:
        self.created = indexes


@pytest.mark.asyncio
async def test_active_run_index_migrates_to_partial_unique_index() -> None:
    collection = _FakeCollection()
    database = SimpleNamespace(personalized_recommendation_runs=collection)

    await _ensure_personalized_recommendation_indexes(database)

    assert collection.dropped == [_LEGACY_ACTIVE_RECOMMENDATION_INDEX]
    active_index = next(
        model.document
        for model in collection.created
        if model.document.get("name") == _ACTIVE_RECOMMENDATION_INDEX
    )
    assert active_index["unique"] is True
    assert active_index["partialFilterExpression"] == {"active_profile_key": {"$type": "string"}}
    assert "sparse" not in active_index
