"""JWT validation against Keycloak JWKS."""

from typing import Any

import jwt
from jwt.algorithms import RSAAlgorithm

from verdeai_shared.auth.jwks import get_public_key
from verdeai_shared.auth.principal import Principal
from verdeai_shared.settings import settings  # noqa: F401 — used for admin_email_set()


class AuthError(Exception):
    """Raised for any authentication failure (401)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class TenantClaimMissing(Exception):
    """Raised when tenant_id claim is absent from a valid token (403)."""

    def __init__(self) -> None:
        super().__init__("tenant_id claim missing from token")


async def decode_token(token: str) -> Principal:
    """Validate a Keycloak bearer token and return a Principal.

    Raises:
        AuthError: on invalid signature, expired token, wrong issuer/audience.
        TenantClaimMissing: if the token is otherwise valid but has no tenant_id.
    """
    # Step 1: Decode header only to extract kid
    try:
        header: dict[str, Any] = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as exc:
        raise AuthError(f"Invalid token format: {exc}") from exc

    kid: str = header.get("kid", "")
    if not kid:
        raise AuthError("JWT header missing 'kid'")

    # Step 2: Fetch public key (with one-shot refresh on miss)
    try:
        jwk = await get_public_key(kid, allow_refresh=True)
    except KeyError as exc:
        raise AuthError(str(exc)) from exc

    public_key = RSAAlgorithm.from_jwk(jwk)

    # Step 3: Decode without issuer check first, then validate manually.
    # Keycloak embeds KC_HOSTNAME in the iss claim (may differ from the internal
    # KEYCLOAK_URL used for JWKS fetching), so we accept both URLs.
    audience = [settings.KEYCLOAK_FRONTEND_CLIENT_ID, "account"]
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_iss": False},
            audience=audience,
            leeway=settings.KEYCLOAK_TOKEN_LEEWAY_SECONDS,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError("Invalid audience") from exc
    except jwt.PyJWTError as exc:
        raise AuthError(f"Token validation failed: {exc}") from exc

    # Manual issuer check — accept internal or public Keycloak URL
    realm_path = f"/realms/{settings.KEYCLOAK_REALM}"
    valid_issuers = {
        f"{settings.KEYCLOAK_URL}{realm_path}",
        f"{settings.KEYCLOAK_PUBLIC_URL}{realm_path}",
    }
    token_iss: str = payload.get("iss", "")
    if token_iss not in valid_issuers:
        raise AuthError("Invalid issuer")

    # Step 4: Extract tenant_id — mandatory
    tenant_id: str | None = payload.get("tenant_id")
    if not tenant_id:
        raise TenantClaimMissing()

    # Step 5: Build Principal
    realm_access: dict[str, Any] = payload.get("realm_access", {})
    roles: list[str] = list(realm_access.get("roles", []))

    # Belt-and-suspenders: grant admin if email is in ADMIN_EMAILS env list
    email: str = payload.get("email", "")
    if email.lower() in settings.admin_email_set() and "admin" not in roles:
        roles.append("admin")

    return Principal(
        sub=payload["sub"],
        tenant_id=tenant_id,
        email=email,
        roles=roles,
        first_name=payload.get("given_name"),
        last_name=payload.get("family_name"),
    )
