"""Global exception handlers producing the uniform error envelope.

Registered on the app by :func:`register_exception_handlers`. Every handler
emits an :class:`~inkstave.errors.ErrorEnvelope`, carries the request id (in the
body and the response header), and never leaks internals for unexpected errors.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from inkstave.config import get_settings
from inkstave.errors import AppError, ErrorBody, ErrorEnvelope
from inkstave.logging import get_request_id

logger = logging.getLogger("inkstave.error")


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


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    # Log the full traceback; never return it to the client.
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


def register_exception_handlers(app: FastAPI) -> None:
    """Register all handlers on ``app``."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
