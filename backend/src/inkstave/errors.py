"""Error types and the uniform error envelope.

Every error response in the API shares one shape (:class:`ErrorEnvelope`). The
:class:`AppError` hierarchy lets feature code raise typed, machine-readable
errors that the exception handlers turn into that envelope.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """The ``error`` object carried by every error response."""

    type: str = Field(description="Machine-readable, snake_case error code.")
    message: str = Field(description="Human-readable summary of the error.")
    details: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional structured detail (e.g. per-field validation errors).",
    )
    request_id: str | None = Field(
        default=None,
        description="Correlation id of the request that produced the error.",
    )


class ErrorEnvelope(BaseModel):
    """Top-level envelope wrapping an :class:`ErrorBody`."""

    error: ErrorBody


class AppError(Exception):
    """Base class for expected, typed application errors.

    Subclasses set ``status_code`` and ``error_type``; raising one anywhere in a
    request results in the matching HTTP status and a populated error envelope.
    """

    status_code: int = 500
    error_type: str = "app_error"

    def __init__(
        self,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        # Extra response headers (e.g. WWW-Authenticate, Retry-After).
        self.headers = headers


class BadRequestError(AppError):
    status_code = 400
    error_type = "bad_request"


class UnauthorizedError(AppError):
    status_code = 401
    error_type = "unauthorized"

    def __init__(
        self,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        # A 401 always advertises the scheme to use to authenticate.
        super().__init__(
            message, details=details, headers=headers or {"WWW-Authenticate": "Bearer"}
        )


class ForbiddenError(AppError):
    status_code = 403
    error_type = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    error_type = "not_found"


class ConflictError(AppError):
    status_code = 409
    error_type = "conflict"


class RateLimitError(AppError):
    status_code = 429
    error_type = "rate_limited"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many requests.",
            headers={"Retry-After": str(retry_after_seconds)},
        )
