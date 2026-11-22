"""Global exception handlers producing the uniform error envelope.

Registered on the app by :func:`register_exception_handlers`. Every handler
emits an :class:`~inkstave.core.errors.ErrorEnvelope`, carries the request id (in the
body and the response header), and never leaks internals for unexpected errors.

:class:`UnhandledErrorMiddleware` is the one place an uncaught exception becomes a
500: it runs inside CORS and the security headers, so that response carries them too.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from inkstave.core.config.settings import get_settings
from inkstave.core.errors import AppError, ErrorBody, ErrorEnvelope
from inkstave.core.logging import get_request_id

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("inkstave.error")

# Error types for the HTTP statuses Starlette raises itself (unknown route, wrong method).
_HTTP_ERROR_TYPES = {404: "not_found", 405: "method_not_allowed"}


def _envelope_response(
    *,
    status_code: int,
    error_type: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id()
    body = ErrorEnvelope(
        error=ErrorBody(
            type=error_type,
            message=message,
            details=details,
            request_id=request_id,
        )
    )
    response = JSONResponse(status_code=status_code, content=body.model_dump())
    if headers:
        response.headers.update(headers)
    if request_id is not None:
        settings = get_settings()
        response.headers[settings.request_id_header] = request_id
    return response


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return _envelope_response(
        status_code=exc.status_code,
        error_type=exc.error_type,
        message=exc.message,
        details=exc.details,
        headers=exc.headers,
    )


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Normalise pydantic errors into JSON-serialisable detail dicts.
    details = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return _envelope_response(
        status_code=422,
        error_type="validation_error",
        message="Request validation failed",
        details=details,
    )


async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Routing's own 404 and 405 (and any bare HTTP status), in the envelope."""
    return _envelope_response(
        status_code=exc.status_code,
        error_type=_HTTP_ERROR_TYPES.get(exc.status_code, "http_error"),
        message=str(exc.detail),
        headers=dict(exc.headers) if exc.headers else None,
    )


def unhandled_error_response(exc: Exception) -> JSONResponse:
    """Log the traceback and build the 500 envelope; the traceback never reaches the client."""
    logger.exception("Unhandled exception", exc_info=exc)
    settings = get_settings()
    message = "Internal server error"
    if settings.debug:
        message = f"Internal server error: {type(exc).__name__}"
    return _envelope_response(
        status_code=500,
        error_type="internal_error",
        message=message,
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    # Fallback for an exception that escapes UnhandledErrorMiddleware (none in practice).
    return unhandled_error_response(exc)


class UnhandledErrorMiddleware:
    """Answer an uncaught exception with the 500 envelope, while the response is still ours to write.

    Placed inside CORS and the security headers, and inside RequestContextMiddleware, so the
    500 carries the request id, the X-Request-ID header, the security headers and CORS headers.
    If the response had already started, the exception cannot be answered and is re-raised.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:
                raise
            await unhandled_error_response(exc)(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all handlers on ``app``."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
