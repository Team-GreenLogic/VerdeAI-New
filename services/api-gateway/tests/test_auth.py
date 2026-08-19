"""Tests for /auth/register endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from verdeai_shared.auth.principal import Principal


@pytest.fixture
def client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


VALID_REGISTER_PAYLOAD = {
    "email": "test@example.com",
    "password": "SecurePass!23",
    "first_name": "Test",
    "last_name": "User",
    "organisation_name": "Test Corp",
}


def test_register_success(client: TestClient) -> None:
    fake_sub = "kc-user-uuid-123"
    fake_user_id = "mongo-doc-id-abc"

    with (
        patch(
            "app.routers.auth.create_user",
            return_value=fake_sub,
        ),
        patch("app.routers.auth.assign_realm_role"),
        patch("app.routers.auth.get_database") as mock_db,
    ):
        mock_col = AsyncMock()
        mock_col.update_one = AsyncMock()
        mock_col.find_one = AsyncMock(
            return_value={"_id": MagicMock(__str__=lambda s: fake_user_id), "keycloak_sub": fake_sub}
        )
        mock_db.return_value.users = mock_col

        response = client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)

    assert response.status_code == 201
    data = response.json()
    assert "tenant_id" in data
    assert data["keycloak_sub"] == fake_sub
    assert len(data["tenant_id"]) == 36  # UUID v4


def test_register_duplicate_email(client: TestClient) -> None:
    with patch(
        "app.routers.auth.create_user",
        side_effect=Exception("409 Conflict: User already exists"),
    ):
        response = client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)

    assert response.status_code == 409


def test_register_invalid_payload(client: TestClient) -> None:
    response = client.post("/auth/register", json={"email": "not-an-email"})
    assert response.status_code == 422


def test_register_keycloak_error(client: TestClient) -> None:
    with patch(
        "app.routers.auth.create_user",
        side_effect=Exception("Connection refused"),
    ):
        response = client.post("/auth/register", json=VALID_REGISTER_PAYLOAD)

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_me_returns_display_name_from_identity_claims() -> None:
    from app.routers.auth import me

    response = await me(Principal(
        sub="user-1",
        tenant_id="tenant-1",
        email="maya@example.com",
        roles=["compliance-officer"],
        first_name="Maya",
        last_name="Silva",
    ))

    assert response.display_name == "Maya Silva"
    assert response.first_name == "Maya"
    assert response.last_name == "Silva"


@pytest.mark.asyncio
async def test_me_allows_existing_tokens_without_name_claims() -> None:
    from app.routers.auth import me

    response = await me(Principal(
        sub="user-1",
        tenant_id="tenant-1",
        email="legacy@example.com",
        roles=[],
    ))

    assert response.display_name is None

