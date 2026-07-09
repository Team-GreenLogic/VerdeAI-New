"""Request-scoped tenant context var and FastAPI dependency."""

from contextvars import ContextVar
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from verdeai_shared.auth.principal import Principal
from verdeai_shared.auth.token import AuthError, TenantClaimMissing, decode_token

_principal_var: ContextVar[Principal | None] = ContextVar("_principal", default=None)

_bearer = HTTPBearer(auto_error=False)


def get_tenant_id() -> str:
    """Return the current request's tenant_id from the context var.

    Raises RuntimeError if called outside a request context with a set principal.
    """
    principal = _principal_var.get()
    if principal is None:
        raise RuntimeError("No principal set in context — call outside auth dependency?")
    return principal.tenant_id


def get_principal() -> Principal:
    """Return the current request's Principal."""
    principal = _principal_var.get()
    if principal is None:
        raise RuntimeError("No principal set in context")
    return principal


async def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """FastAPI dependency: validates Keycloak JWT and writes Principal to context var."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        principal = await decode_token(credentials.credentials)
    except TenantClaimMissing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is missing the tenant_id claim",
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    _principal_var.set(principal)
    return principal


# Type alias for use in route signatures
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


async def require_admin(principal: Annotated[Principal, Depends(get_current_principal)]) -> Principal:
    """FastAPI dependency: raises 403 unless the principal holds the 'admin' role."""
    if "admin" not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return principal


CurrentAdmin = Annotated[Principal, Depends(require_admin)]
