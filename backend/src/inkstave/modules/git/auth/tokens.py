"""Personal access tokens for Git (spec 121): create, list, revoke and authenticate.

A token is ``ink_`` followed by 43 URL-safe characters. Only its SHA-256 hash is stored (the same hash
the auth module uses for its one-time links); the raw value is returned once, at creation. A token is
accepted only on the Git routes, as the password of HTTP Basic authentication.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select

from inkstave.core.errors import ConflictError, NotFoundError
from inkstave.modules.auth import generate_token, hash_token
from inkstave.modules.auth.models.user import User
from inkstave.modules.git.models import GitAccessToken

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

TOKEN_PREFIX = "ink_"  # noqa: S105 - a visible prefix, not a secret
MAX_ACTIVE_TOKENS = 20
_DISPLAY_LENGTH = 12


class GitTokenLimitError(ConflictError):
    error_type = "token_limit"

    def __init__(self) -> None:
        super().__init__(f"A user may hold at most {MAX_ACTIVE_TOKENS} active Git access tokens.")


class GitTokenNotFoundError(NotFoundError):
    error_type = "token_not_found"

    def __init__(self) -> None:
        super().__init__("Git access token not found.")


@dataclass(frozen=True, slots=True)
class IssuedToken:
    row: GitAccessToken
    raw: str  # shown to the user once


def new_raw_token() -> str:
    return TOKEN_PREFIX + generate_token()


def display_prefix(raw: str) -> str:
    return raw[:_DISPLAY_LENGTH]


def _active_clause(now: datetime) -> ColumnElement[bool]:
    return and_(
        GitAccessToken.revoked_at.is_(None),
        or_(GitAccessToken.expires_at.is_(None), GitAccessToken.expires_at > now),
    )


async def create_token(
    session: AsyncSession, user_id: UUID, name: str, expires_at: datetime | None
) -> IssuedToken:
    now = datetime.now(UTC)
    active = await session.scalar(
        select(func.count())
        .select_from(GitAccessToken)
        .where(GitAccessToken.user_id == user_id, _active_clause(now))
    )
    if (active or 0) >= MAX_ACTIVE_TOKENS:
        raise GitTokenLimitError()
    raw = new_raw_token()
    row = GitAccessToken(
        user_id=user_id,
        name=name,
        token_hash=hash_token(raw),
        prefix=display_prefix(raw),
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    return IssuedToken(row=row, raw=raw)


async def list_tokens(session: AsyncSession, user_id: UUID) -> list[GitAccessToken]:
    """The user's tokens that are still usable, newest first."""
    rows = await session.execute(
        select(GitAccessToken)
        .where(GitAccessToken.user_id == user_id, _active_clause(datetime.now(UTC)))
        .order_by(GitAccessToken.created_at.desc())
    )
    return list(rows.scalars())


async def revoke_token(session: AsyncSession, user_id: UUID, token_id: UUID) -> None:
    row = (
        await session.execute(
            select(GitAccessToken).where(GitAccessToken.id == token_id, GitAccessToken.user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise GitTokenNotFoundError()
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await session.flush()


def basic_password(authorization: str | None) -> str | None:
    """The password of an ``Authorization: Basic`` header, or ``None`` for anything else."""
    if not authorization or not authorization.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(authorization[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, ValueError):
        return None
    _, sep, password = decoded.partition(":")
    return password if sep and password else None


async def authenticate(session: AsyncSession, raw: str) -> tuple[User, GitAccessToken] | None:
    """The user and token for a presented token, or ``None`` when it is unknown, revoked, expired or
    belongs to an inactive account. A success stamps ``last_used_at``."""
    if not raw.startswith(TOKEN_PREFIX):
        return None
    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(GitAccessToken, User)
            .join(User, User.id == GitAccessToken.user_id)
            .where(
                GitAccessToken.token_hash == hash_token(raw),
                _active_clause(now),
                User.is_active.is_(True),
            )
        )
    ).first()
    if row is None:
        return None
    token, user = row
    token.last_used_at = now
    await session.flush()
    return user, token
