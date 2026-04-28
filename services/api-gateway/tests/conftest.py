"""Test configuration — stubs out external connections for unit tests."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def mock_external_connections():
    """Prevent lifespan from making real DB/broker connections during unit tests."""
    with (
        patch("verdeai_shared.db.indexes.ensure_indexes", new=AsyncMock()),
        patch("verdeai_shared.db.mongo.get_database", return_value=AsyncMock()),
        patch("verdeai_shared.db.mongo.close_client", new=AsyncMock()),
        patch("verdeai_shared.messaging.connection.close_connection", new=AsyncMock()),
        patch("verdeai_shared.llm.openrouter_client.aclose", new=AsyncMock()),
    ):
        yield
