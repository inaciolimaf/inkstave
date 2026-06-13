"""Single-use, hashed-at-rest link-token store for the email auth flows (spec 104).

The only code that creates or consumes ``auth_tokens`` rows. Tokens are hashed
with the spec-59 helpers (``generate_token`` / ``hash_token``); the raw token is
returned exactly once (for the emailed URL) and never persisted or logged. All
time math goes through an injected :class:`~inkstave.time.Clock` so expiry is
deterministic in tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from inkstave.db.models.auth_token import AuthToken
from inkstave.errors import BadRequestError, GoneError
from inkstave.services.sharing_common import generate_token, hash_token
from inkstave.time import SYSTEM_CLOCK, Clock

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("inkstave.auth_tokens")

PURPOSES = ("email_verify", "magic_login", "password_reset")

# One uniform message for unknown / used / wrong-purpose tokens: a used link and
# an unknown link must be indistinguishable to the caller (non-enumeration).
_INVALID = "Invalid or already-used link."
_EXPIRED = "This link has expired."


@dataclass(frozen=True)
class IssuedToken:
    raw: str  # goes only into the emailed URL — never logged or persisted
    token: AuthToken  # the persisted row (hash only)


async def issue_token(
    session: AsyncSession,
    *,
    user_id: UUID,
    email: str,
    purpose: str,
    ttl_seconds: int,
    clock: Clock = SYSTEM_CLOCK,
) -> IssuedToken:
    """Issue a fresh single-use token, superseding any outstanding one.

    A new request invalidates every active token of the same ``(user_id,
    purpose)`` — the most recent link is the only valid one. Only the hash is
    stored; the raw token is returned once.
    """
    if purpose not in PURPOSES:  # pragma: no cover - guarded by callers
        raise ValueError(f"unknown auth-token purpose: {purpose}")

    now = clock.now()
    # 1. Invalidate older active tokens of the same (user, purpose).
    await session.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )

    # 2. Insert the new row (hash only).
    raw = generate_token()
    row = AuthToken(
        purpose=purpose,
        user_id=user_id,
        email=email,
        token_hash=hash_token(raw),
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    session.add(row)
    await session.flush()

    # 3. Security event (spec 51): purpose + user only, never the raw/hash.
    logger.info("auth_token_issued", extra={"user_id": user_id, "purpose": purpose})
    return IssuedToken(raw=raw, token=row)


async def consume_token(
    session: AsyncSession,
    *,
    raw_token: str,
    purpose: str,
    clock: Clock = SYSTEM_CLOCK,
) -> AuthToken:
    """Atomically spend a token, returning the row, or raise.

    Looks the row up only by ``token_hash`` (an unknown token simply misses) and
    filters by ``purpose`` so a verify token can never be redeemed at the reset
    callback. Single-use is enforced inside the caller's transaction (so a crash
    mid-action does not burn the token without effect); a ``SELECT ... FOR UPDATE``
    on the row prevents a double-spend race on two simultaneous clicks.

    Raises:
        BadRequestError: unknown, already-used, or wrong-purpose token (uniform).
        GoneError: an unexpired-but-real token whose ``expires_at`` has passed.
    """
    token_hash = hash_token(raw_token)
    row = await session.scalar(
        select(AuthToken)
        .where(AuthToken.token_hash == token_hash, AuthToken.purpose == purpose)
        .with_for_update()
    )
    if row is None or row.consumed_at is not None:
        # Unknown / used / wrong-purpose all look identical (non-enumeration).
        logger.info("auth_token_invalid", extra={"purpose": purpose, "outcome": "invalid"})
        raise BadRequestError(_INVALID)
    if row.expires_at < clock.now():
        # Distinct from invalid: an expired-but-real link tells the user to
        # request a fresh one. The link was only ever sent to the address owner,
        # so this leaks nothing.
        logger.info(
            "auth_token_consumed",
            extra={"user_id": row.user_id, "purpose": purpose, "outcome": "expired"},
        )
        raise GoneError(_EXPIRED)

    row.consumed_at = clock.now()
    await session.flush()
    logger.info(
        "auth_token_consumed",
        extra={"user_id": row.user_id, "purpose": purpose, "outcome": "ok"},
    )
    return row
