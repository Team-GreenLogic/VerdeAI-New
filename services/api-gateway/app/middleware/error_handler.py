"""Global error handler middleware."""

import traceback

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        try:
            response: Response = await call_next(request)  # type: ignore[arg-type]
            return response
        except Exception as exc:
            logger.error(
                "Unhandled exception",
                path=request.url.path,
                method=request.method,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
