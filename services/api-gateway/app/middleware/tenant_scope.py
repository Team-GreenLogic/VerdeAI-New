"""Tenant scope middleware — ensures tenant_id ContextVar is set before handlers run.

The actual ContextVar write is done in the auth dependency (get_current_principal).
This middleware is a no-op safety wrapper that does not read request body/headers
for tenant_id — it only exists for structural clarity.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TenantScopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        response: Response = await call_next(request)  # type: ignore[arg-type]
        return response
