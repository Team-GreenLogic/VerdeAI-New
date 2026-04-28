"""Request ID middleware — injects X-Request-ID into every request/response."""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        from collections.abc import Callable, Awaitable
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        # Attach to request state for downstream use
        request.state.request_id = request_id
        response: Response = await call_next(request)  # type: ignore[arg-type]
        response.headers["X-Request-ID"] = request_id
        return response
