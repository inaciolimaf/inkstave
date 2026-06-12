"""Unit tests for the auth guards that need no database connection."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from inkstave.auth.dependencies import (
    AdminRequiredError,
    NotAuthenticatedError,
    get_current_user,
    require_admin,
)
from inkstave.db.models.user import User


def _user(*, is_admin: bool) -> User:
    return User(
        id=uuid4(),
        email="user@example.com",
        hashed_password="x",
        display_name="User",
        is_admin=is_admin,
    )


async def test_get_current_user_without_credentials_raises_401() -> None:
    with pytest.raises(NotAuthenticatedError):
        await get_current_user(credentials=None, token_service=None, session=None)  # type: ignore[arg-type]


async def test_get_current_user_with_empty_token_raises_401() -> None:
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="")
    with pytest.raises(NotAuthenticatedError):
        await get_current_user(credentials=creds, token_service=None, session=None)  # type: ignore[arg-type]


async def test_get_current_user_with_non_bearer_scheme_raises_401() -> None:
    """A non-Bearer Authorization header (e.g. ``Authorization: Basic xxx``) → 401.

    ``HTTPBearer(auto_error=False)`` returns ``None`` for any non-Bearer scheme,
    so the ``bearer_scheme`` dependency feeds ``None`` into ``get_current_user``.
    We assert the guard maps that to a 401 ``NotAuthenticatedError``.
    """
    # What FastAPI's HTTPBearer hands the guard for a non-Bearer header.
    non_bearer_resolved = None
    with pytest.raises(NotAuthenticatedError):
        await get_current_user(
            credentials=non_bearer_resolved,  # type: ignore[arg-type]
            token_service=None,  # type: ignore[arg-type]
            session=None,  # type: ignore[arg-type]
        )


def test_not_authenticated_error_carries_www_authenticate() -> None:
    err = NotAuthenticatedError()
    assert err.status_code == 401
    assert err.headers == {"WWW-Authenticate": "Bearer"}


async def test_require_admin_rejects_non_admin() -> None:
    with pytest.raises(AdminRequiredError):
        await require_admin(user=_user(is_admin=False))


async def test_require_admin_allows_admin() -> None:
    admin = _user(is_admin=True)
    assert await require_admin(user=admin) is admin


def test_admin_required_error_is_403() -> None:
    err: Any = AdminRequiredError()
    assert err.status_code == 403
    assert err.message == "Admin privileges required."
