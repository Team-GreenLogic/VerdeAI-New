"""Analysis response collections use numeric ISO clause ordering."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.analyses import (
    get_analysis_results,
    get_missing_requirements,
    get_recommendations,
)
from verdeai_shared.auth.principal import Principal


def _principal() -> Principal:
    return Principal(
        sub="user-1",
        tenant_id="tenant-1",
        email="user@example.com",
        roles=["compliance-officer"],
    )


def _database_with(collection_name: str, rows: list[dict[str, object]]) -> MagicMock:
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows)
    collection = MagicMock()
    collection.find.return_value = cursor
    db = MagicMock()
    setattr(db, collection_name, collection)
    return db


@pytest.mark.asyncio
async def test_gap_results_are_returned_in_numeric_clause_order() -> None:
    db = _database_with("result_store", [
        {"clause_id": "10.1", "decision": "Met"},
        {"clause_id": "4.2", "decision": "Met"},
        {"clause_id": "4.1", "decision": "Met"},
    ])

    with (
        patch("app.routers.analyses.get_database", return_value=db),
        patch("app.routers.analyses._get_owned", new=AsyncMock()),
    ):
        results = await get_analysis_results("analysis-1", _principal())

    assert [result.clause_id for result in results] == ["4.1", "4.2", "10.1"]


@pytest.mark.asyncio
async def test_recommendations_use_numeric_clauses_as_default_and_tie_break_order() -> None:
    db = _database_with("recommendation_store", [
        {"clause_id": "10.1", "text": "ten", "impact": 2},
        {"clause_id": "4.2", "text": "four two", "impact": 3},
        {"clause_id": "4.1", "text": "four one", "impact": 3},
    ])

    with (
        patch("app.routers.analyses.get_database", return_value=db),
        patch("app.routers.analyses._get_owned", new=AsyncMock()),
    ):
        default_results = await get_recommendations("analysis-1", _principal())
        impact_results = await get_recommendations(
            "analysis-1", _principal(), sort_by="impact", order="desc"
        )

    assert [result.clause_id for result in default_results] == ["4.1", "4.2", "10.1"]
    assert [result.clause_id for result in impact_results] == ["4.1", "4.2", "10.1"]


@pytest.mark.asyncio
async def test_missing_requirements_are_returned_in_numeric_clause_order() -> None:
    db = _database_with("missing_request_store", [
        {"clause_id": "10.1", "request_text": "ten"},
        {"clause_id": "4.2", "request_text": "four two"},
        {"clause_id": "4.1", "request_text": "four one"},
    ])

    with (
        patch("app.routers.analyses.get_database", return_value=db),
        patch("app.routers.analyses._get_owned", new=AsyncMock()),
    ):
        results = await get_missing_requirements("analysis-1", _principal())

    assert [result.clause_id for result in results] == ["4.1", "4.2", "10.1"]
