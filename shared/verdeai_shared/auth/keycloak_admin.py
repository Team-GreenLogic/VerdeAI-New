"""python-keycloak admin client wrapper — used by api-gateway only."""

from typing import Any

from keycloak import KeycloakAdmin  # type: ignore[import-untyped]

from verdeai_shared.settings import settings

_admin: KeycloakAdmin | None = None


def _reset() -> None:
    """Force a new connection on the next call (e.g. after token expiry)."""
    global _admin
    _admin = None


def get_admin_client() -> KeycloakAdmin:
    """Return a KeycloakAdmin instance.

    Uses the bootstrap admin username/password (master-realm admin) to manage
    the verdeai realm. This is simpler than the client-credentials flow for
    Phase 0 and doesn't require the verdeai-admin client secret to be
    pre-configured.
    """
    global _admin
    if _admin is None:
        _admin = KeycloakAdmin(
            server_url=settings.KEYCLOAK_URL + "/",
            username=settings.KEYCLOAK_ADMIN_USER,
            password=settings.KEYCLOAK_ADMIN_PASSWORD,
            realm_name=settings.KEYCLOAK_REALM,
            user_realm_name="master",
            verify=True,
        )
    return _admin


def create_user(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    tenant_id: str,
) -> str:
    """Create a Keycloak user with the tenant_id attribute. Returns the Keycloak user ID (sub)."""
    admin = get_admin_client()
    user_id: str = admin.create_user(
        {
            "email": email,
            "username": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "credentials": [
                {"type": "password", "value": password, "temporary": False}
            ],
            "attributes": {"tenant_id": [tenant_id]},
        }
    )
    return user_id


def assign_realm_role(user_id: str, role_name: str) -> None:
    """Assign a realm-level role to a user."""
    admin = get_admin_client()
    role: dict[str, Any] = admin.get_realm_role(role_name)
    admin.assign_realm_roles(user_id=user_id, roles=[role])
