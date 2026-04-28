"""Tests for JWT token validation logic."""

import time
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from verdeai_shared.auth.token import AuthError, TenantClaimMissing, decode_token


def _make_token(
    payload: dict,  # type: ignore[type-arg]
    private_key: str,
    kid: str = "test-kid",
    algorithm: str = "RS256",
) -> str:
    headers = {"kid": kid}
    return jwt.encode(payload, private_key, algorithm=algorithm, headers=headers)


@pytest.fixture
def rsa_key_pair() -> tuple[str, str]:
    """Generate a throwaway RSA key pair for testing."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


@pytest.mark.asyncio
async def test_decode_valid_token(rsa_key_pair: tuple[str, str]) -> None:
    private_pem, public_pem = rsa_key_pair
    now = int(time.time())
    payload = {
        "sub": "user-uuid-123",
        "tenant_id": "tenant-uuid-456",
        "email": "test@example.com",
        "realm_access": {"roles": ["compliance-officer"]},
        "iss": "http://keycloak:8080/realms/verdeai",
        "aud": ["verdeai-frontend"],
        "exp": now + 300,
        "iat": now,
    }
    token = _make_token(payload, private_pem)

    # Mock get_public_key to return a JWK-like dict that jwt can use
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
    import cryptography.hazmat.primitives.asymmetric.rsa as _rsa_mod

    # Build a JWK from the public key
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from jwt.algorithms import RSAAlgorithm
    pub = load_pem_public_key(public_pem.encode())
    jwk_dict = RSAAlgorithm.to_jwk(pub, as_dict=True)

    with patch("verdeai_shared.auth.token.get_public_key", new=AsyncMock(return_value=jwk_dict)):
        principal = await decode_token(token)

    assert principal.sub == "user-uuid-123"
    assert principal.tenant_id == "tenant-uuid-456"
    assert principal.email == "test@example.com"
    assert "compliance-officer" in principal.roles


@pytest.mark.asyncio
async def test_decode_expired_token(rsa_key_pair: tuple[str, str]) -> None:
    private_pem, public_pem = rsa_key_pair
    now = int(time.time())
    payload = {
        "sub": "user-uuid-123",
        "tenant_id": "tenant-uuid-456",
        "email": "test@example.com",
        "realm_access": {"roles": []},
        "iss": "http://keycloak:8080/realms/verdeai",
        "aud": ["verdeai-frontend"],
        "exp": now - 1000,
        "iat": now - 2000,
    }
    token = _make_token(payload, private_pem)

    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from jwt.algorithms import RSAAlgorithm
    pub = load_pem_public_key(public_pem.encode())
    jwk_dict = RSAAlgorithm.to_jwk(pub, as_dict=True)

    with patch("verdeai_shared.auth.token.get_public_key", new=AsyncMock(return_value=jwk_dict)):
        with pytest.raises(AuthError, match="expired"):
            await decode_token(token)


@pytest.mark.asyncio
async def test_decode_missing_tenant_id(rsa_key_pair: tuple[str, str]) -> None:
    private_pem, public_pem = rsa_key_pair
    now = int(time.time())
    payload = {
        "sub": "user-uuid-123",
        # No tenant_id claim!
        "email": "test@example.com",
        "realm_access": {"roles": []},
        "iss": "http://keycloak:8080/realms/verdeai",
        "aud": ["verdeai-frontend"],
        "exp": now + 300,
        "iat": now,
    }
    token = _make_token(payload, private_pem)

    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from jwt.algorithms import RSAAlgorithm
    pub = load_pem_public_key(public_pem.encode())
    jwk_dict = RSAAlgorithm.to_jwk(pub, as_dict=True)

    with patch("verdeai_shared.auth.token.get_public_key", new=AsyncMock(return_value=jwk_dict)):
        with pytest.raises(TenantClaimMissing):
            await decode_token(token)


@pytest.mark.asyncio
async def test_decode_bad_format_token() -> None:
    with pytest.raises(AuthError):
        await decode_token("not.a.token")
