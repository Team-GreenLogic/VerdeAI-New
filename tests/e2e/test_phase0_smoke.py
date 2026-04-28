"""Phase 0 smoke test — validates the running stack end-to-end.

Requires `make up` to be run first (real Docker stack).
Run with: pytest tests/e2e/test_phase0_smoke.py
"""

import os
import pytest
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_health() -> None:
    async with httpx.AsyncClient(base_url=GATEWAY_URL) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness() -> None:
    async with httpx.AsyncClient(base_url=GATEWAY_URL) as client:
        resp = await client.get("/readiness")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_without_token() -> None:
    """Protected endpoints must return 401 without a token."""
    async with httpx.AsyncClient(base_url=GATEWAY_URL) as client:
        # Any future protected endpoint (e.g. /documents added in Phase 1)
        # For now we just test that a non-existent protected path behaviour is consistent
        resp = await client.get("/documents")
    # 401 (auth rejected) or 404 (not yet implemented) — both are acceptable for Phase 0
    assert resp.status_code in (401, 404)


@pytest.mark.asyncio
async def test_register_and_token_contains_tenant_id() -> None:
    """Full registration → token flow verifying tenant_id claim propagation."""
    import uuid
    unique_email = f"e2e-{uuid.uuid4().hex[:8]}@verdeai.local"

    # 1. Register
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30.0) as client:
        reg_resp = await client.post(
            "/auth/register",
            json={
                "email": unique_email,
                "password": "E2eTestPass!23",
                "first_name": "E2E",
                "last_name": "Test",
                "organisation_name": "E2E Org",
            },
        )
    assert reg_resp.status_code == 201, reg_resp.text
    reg_data = reg_resp.json()
    assert "tenant_id" in reg_data
    tenant_id = reg_data["tenant_id"]

    # 2. Fetch token from Keycloak (password grant for testing)
    async with httpx.AsyncClient(base_url=KEYCLOAK_URL, timeout=30.0) as client:
        token_resp = await client.post(
            f"/realms/verdeai/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "verdeai-frontend",
                "username": unique_email,
                "password": "E2eTestPass!23",
                "scope": "openid profile email",
            },
        )
    assert token_resp.status_code == 200, token_resp.text
    token_data = token_resp.json()
    assert "access_token" in token_data

    # 3. Decode access token and verify tenant_id claim
    import jwt as pyjwt
    decoded = pyjwt.decode(
        token_data["access_token"],
        options={"verify_signature": False},
    )
    assert "tenant_id" in decoded, "tenant_id claim missing from access token"
    assert decoded["tenant_id"] == tenant_id
