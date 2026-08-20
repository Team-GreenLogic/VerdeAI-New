"""Failure handling contracts for personalized recommendation jobs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from verdeai_shared.messaging.events import PersonalizedRecommendationRequested

from app.actors import handle_personalized_recommendation_requested


@pytest.mark.asyncio
async def test_failure_persistence_error_does_not_requeue_forever() -> None:
    event = PersonalizedRecommendationRequested(
        tenant_id="tenant-1",
        profile_id="profile-1",
        analysis_id="analysis-1",
        run_id="run-1",
    )
    message = SimpleNamespace(body=event.model_dump_json().encode())
    update_one = AsyncMock(side_effect=RuntimeError("database unavailable"))
    database = SimpleNamespace(
        personalized_recommendation_runs=SimpleNamespace(update_one=update_one)
    )
    emit = AsyncMock()

    with (
        patch("app.actors.get_database", return_value=database),
        patch(
            "app.actors.run_with_timeout",
            new=AsyncMock(side_effect=RuntimeError("research failed")),
        ),
        patch("app.actors.emit", new=emit),
    ):
        await handle_personalized_recommendation_requested(message)

    update_one.assert_awaited_once()
    emit.assert_awaited_once_with(
        "tenant-1",
        "run-1",
        "failed",
        "failed",
        "Research failed. You can generate another run.",
    )
