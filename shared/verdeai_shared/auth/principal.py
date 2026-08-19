"""Principal model — the authenticated identity extracted from a Keycloak JWT."""

from pydantic import BaseModel


class Principal(BaseModel):
    """Validated identity from a Keycloak access token."""

    sub: str          # Keycloak user UUID
    tenant_id: str    # from custom claim — required; fail if missing
    email: str
    roles: list[str]  # from realm_access.roles
    first_name: str | None = None
    last_name: str | None = None
