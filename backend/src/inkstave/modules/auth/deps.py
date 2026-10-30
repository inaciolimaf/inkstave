"""FastAPI authentication guards and the WebSocket auth helper (spec 08).

* ``get_current_user`` — require a valid Bearer **access** token; load the user.
* ``require_admin`` — additionally require the **DB** ``is_admin`` flag.
* ``get_optional_user`` — ``None`` when no token is sent, but ``401`` if a token
  is sent and is invalid.
* ``authenticate_ws_token`` — the same validation a future WebSocket will use.

401s carry ``WWW-Authenticate: Bearer`` (via :class:`UnauthorizedError`). 403
means authenticated-but-not-permitted (do not retry as the same user).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from inkstave.core.config.settings import Settings
from inkstave.core.db.session import get_db_session
from inkstave.core.deps import get_redis, get_settings_dep
from inkstave.core.errors import ForbiddenError, UnauthorizedError
from inkstave.core.observability.context import bind_context
from inkstave.modules.auth.credentials.password import PasswordHasher, build_password_hasher
from inkstave.modules.auth.credentials.refresh_store import RefreshStore, build_refresh_store
from inkstave.modules.auth.credentials.tokens import TokenError, TokenService, build_token_service
from inkstave.modules.auth.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def get_password_hasher(
    settings: Settings = Depends(get_settings_dep),
) -> PasswordHasher:
    """Dependency providing an argon2 password hasher built from settings."""
    return build_password_hasher(settings)


def get_token_service(
    settings: Settings = Depends(get_settings_dep),
) -> TokenService:
    """Dependency providing the JWT token service built from settings."""
    return build_token_service(settings)


def get_refresh_store(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> RefreshStore:
    """Dependency providing the Redis-backed refresh-token store."""
    return build_refresh_store(get_redis(request), settings)


# auto_error=False so we emit the project's error envelope rather than FastAPI's
# default; the same scheme serves required and optional auth.
bearer_scheme = HTTPBearer(auto_error=False)


class NotAuthenticatedError(UnauthorizedError):
    """401 — no/invalid/expired token, or the token's user no longer exists."""

    def __init__(self) -> None:
        super().__init__("Not authenticated.")


class AdminRequiredError(ForbiddenError):
    """403 — authenticated but not an administrator."""

    def __init__(self) -> None:
        super().__init__("Admin privileges required.")


async def _resolve_user(token: str, token_service: TokenService, session: AsyncSession) -> User:
    """Validate an access token and load its user, or raise 401."""
    try:
        claims = token_service.decode_token(token, "access")
    except TokenError as exc:
        raise NotAuthenticatedError() from exc
    user = await session.get(User, UUID(claims["sub"]))
    if user is None:
        raise NotAuthenticatedError()
    # Bind the resolved user to the request context so all later logs carry user_id
    # without the call site threading it (spec 51 §5.2.2).
    bind_context(user_id=str(user.id))
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token_service: TokenService = Depends(get_token_service),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Return the authenticated user, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise NotAuthenticatedError()
    return await _resolve_user(credentials.credentials, token_service, session)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Return the user only if the DB row says they are an admin (authoritative)."""
    if not user.is_admin:
        raise AdminRequiredError()
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token_service: TokenService = Depends(get_token_service),
    session: AsyncSession = Depends(get_db_session),
) -> User | None:
    """Return the user if a valid token is sent, ``None`` if none is sent.

    A token that is *present but invalid* still raises 401.
    """
    if credentials is None or not credentials.credentials:
        return None
    return await _resolve_user(credentials.credentials, token_service, session)


async def authenticate_ws_token(token: str, token_service: TokenService, session: AsyncSession) -> User:
    """Validate a WebSocket auth token exactly like ``get_current_user``.

    Reused by spec 29's WebSocket layer. Raises :class:`NotAuthenticatedError`
    on any invalid/expired token or unknown user.
    """
    return await _resolve_user(token, token_service, session)
