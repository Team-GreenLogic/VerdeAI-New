"""Tests for health and readiness endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


@pytest.fixture
def client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_ok(client: TestClient) -> None:
    with (
        patch(
            "verdeai_shared.db.mongo.get_client",
        ) as mock_mongo,
        patch(
            "verdeai_shared.messaging.connection.get_connection",
            new_callable=AsyncMock,
        ) as mock_rmq,
        patch("redis.asyncio.from_url") as mock_redis,
    ):
        # Mock MongoDB ping
        mock_mongo.return_value.admin.command = AsyncMock(return_value={"ok": 1.0})

        # Mock RabbitMQ connection
        mock_conn = AsyncMock()
        mock_conn.is_closed = False
        mock_rmq.return_value = mock_conn

        # Mock Redis ping
        mock_redis_instance = AsyncMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)
        mock_redis_instance.aclose = AsyncMock()
        mock_redis.return_value = mock_redis_instance

        response = client.get("/readiness")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
