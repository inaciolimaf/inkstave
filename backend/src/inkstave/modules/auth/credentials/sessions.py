"""Ending a session is a server decision: a JWT stays valid until it expires otherwise.

``sv`` (the user's ``session_version``) ends every session of an account at once; ``sid`` ends
one device. The session id is the refresh family: minted at login, kept across rotations, and
carried by the access token as ``sid`` and by the refresh token as ``family_id``.

Tokens issued before these claims existed follow one rule, chosen so a deploy signs nobody out:
a missing ``sv`` counts as 0, which is every account's starting version, so the token lives on
until the account's version moves. A pre-deploy refresh token still has ``family_id``, and its
next rotation yields tokens with both claims. A pre-deploy access token has no ``sid``, so a
logout cannot reach it; it dies on its own within ``ACCESS_TOKEN_TTL_SECONDS``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from inkstave.core.time import SYSTEM_CLOCK, Clock
from inkstave.modules.auth.models.revoked_session import RevokedSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.modules.auth.models.user import User

_VERSION_OF_TOKENS_WITHOUT_ONE = 0


def end_every_session(user: User) -> None:
    """Kill every access and refresh token of the account; the caller's unit of work saves it."""
    user.session_version += 1


async def is_alive(session: AsyncSession, user: User, claims: dict[str, Any]) -> bool:
    """The one check behind every token: active account, same version, session not revoked."""
    if not user.is_active:
        return False
    if claims.get("sv", _VERSION_OF_TOKENS_WITHOUT_ONE) != user.session_version:
        return False
    session_id = claims.get("sid") or claims.get("family_id")
    if session_id is None:
        return True
    revoked = await session.scalar(
        select(RevokedSession.session_id).where(RevokedSession.session_id == UUID(session_id))
    )
    return revoked is None


async def revoke_session(
    session: AsyncSession, session_id: str, *, ttl_seconds: int, clock: Clock = SYSTEM_CLOCK
) -> None:
    """End one session. Its row outlives the family's last refresh token, then gets swept."""
    now = clock.now()
    await session.execute(delete(RevokedSession).where(RevokedSession.expires_at < now))
    await session.execute(
        insert(RevokedSession)
        .values(session_id=UUID(session_id), expires_at=now + timedelta(seconds=ttl_seconds))
        .on_conflict_do_nothing()
    )
