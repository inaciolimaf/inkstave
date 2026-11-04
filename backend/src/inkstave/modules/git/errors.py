"""Errors of the Git access surface (spec 121). Each carries the error envelope's ``type``."""

from __future__ import annotations

from inkstave.core.errors import AppError, BadRequestError, NotFoundError, UnauthorizedError

GIT_CHALLENGE = {"WWW-Authenticate": 'Basic realm="Inkstave"'}


class GitDisabledError(NotFoundError):
    """``GIT_ENABLED`` is off. The routes answer as if they did not exist."""

    def __init__(self) -> None:
        super().__init__("Not found.")


class GitUnauthorizedError(UnauthorizedError):
    """No usable Git access token: unknown, revoked, expired or inactive. 401 with a Basic challenge."""

    def __init__(self) -> None:
        super().__init__("A valid Git access token is required.", headers=dict(GIT_CHALLENGE))


class GitProtocolRequestError(BadRequestError):
    error_type = "git_protocol"


class GitBodyTooLargeError(AppError):
    status_code = 413
    error_type = "payload_too_large"

    def __init__(self) -> None:
        super().__init__("The request body exceeds the allowed size.")


class GitUnsupportedMediaError(AppError):
    status_code = 415
    error_type = "unsupported_media_type"

    def __init__(self, expected: str) -> None:
        super().__init__(f"Expected Content-Type {expected}.")
