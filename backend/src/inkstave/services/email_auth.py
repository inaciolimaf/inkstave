"""Business logic for the three email-link account flows (spec 104).

Verify / magic-login / reset all share the single-use token store
(:mod:`inkstave.services.auth_tokens`). Routes stay thin: they build the URL and
enqueue the email; everything security-sensitive (token binding, single-use,
expiry, session revocation) lives here. The email *delivery* pipeline (spec 103)
is untouched — these flows only replace 103's throwaway token URLs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from inkstave.errors import BadRequestError
from inkstave.schemas.auth import TokenPair
from inkstave.schemas.user import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    validate_password_charset,
)
from inkstave.services.auth import issue_token_pair
from inkstave.services.auth_tokens import consume_token, issue_token
from inkstave.services.user import get_user_by_email
from inkstave.time import SYSTEM_CLOCK, Clock

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.auth.password import PasswordHasher
    from inkstave.auth.refresh_store import RefreshStore
    from inkstave.auth.tokens import TokenService
    from inkstave.config import Settings
    from inkstave.db.models.user import User

logger = logging.getLogger("inkstave.email_auth")


def _validate_new_password(user: User, new_password: str) -> None:
    """Re-apply the spec-06 strength rule (8–72, letter+digit, no email local-part).

    Schema length checks are not sufficient — the service is the trust boundary
    for the token-authorized reset, so it re-validates here (raising 400, never 500).
    """
    if not PASSWORD_MIN_LENGTH <= len(new_password) <= PASSWORD_MAX_LENGTH:
        raise BadRequestError(
            f"Password must be {PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} characters."
        )
    try:
        validate_password_charset(new_password)
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    if user.email.split("@", 1)[0].lower() in new_password.lower():
        raise BadRequestError("Password must not contain your email address.")


# --- email verification ---------------------------------------------------- #


async def request_email_verification(
    session: AsyncSession,
    user: User,
    *,
    settings: Settings,
    clock: Clock = SYSTEM_CLOCK,
) -> str:
    """Issue an ``email_verify`` token bound to the user's current email."""
    issued = await issue_token(
        session,
        user_id=user.id,
        email=user.email,
        purpose="email_verify",
        ttl_seconds=settings.email_verification_token_ttl,
        clock=clock,
    )
    return issued.raw


async def confirm_email_verification(
    session: AsyncSession, *, raw_token: str, clock: Clock = SYSTEM_CLOCK
) -> User:
    """Consume an ``email_verify`` token and set ``email_confirmed``.

    Only confirms if the bound address still equals the user's current email (an
    email change since the link was sent invalidates it). Idempotent: a user that
    is already confirmed still returns 200.
    """
    token = await consume_token(session, raw_token=raw_token, purpose="email_verify", clock=clock)
    user = await _load_user(session, token.user_id)
    if user.email.lower() != token.email.lower():
        raise BadRequestError("Invalid or already-used link.")
    user.email_confirmed = True
    await session.flush()
    return user


# --- magic-link passwordless login ----------------------------------------- #


async def request_magic_login(
    session: AsyncSession,
    *,
    email: str,
    settings: Settings,
    clock: Clock = SYSTEM_CLOCK,
) -> str | None:
    """Issue a ``magic_login`` token, or ``None`` if no such user (non-enumerating)."""
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    issued = await issue_token(
        session,
        user_id=user.id,
        email=user.email,
        purpose="magic_login",
        ttl_seconds=settings.magic_login_token_ttl,
        clock=clock,
    )
    return issued.raw


async def complete_magic_login(
    session: AsyncSession,
    token_service: TokenService,
    refresh_store: RefreshStore,
    *,
    raw_token: str,
    clock: Clock = SYSTEM_CLOCK,
) -> TokenPair:
    """Consume a ``magic_login`` token and issue the real JWT pair (logs the user in).

    Clicking the link proves inbox ownership, so a successful magic login also
    confirms the email. Reuses the exact issuance seam as credential login.
    """
    token = await consume_token(session, raw_token=raw_token, purpose="magic_login", clock=clock)
    user = await _load_user(session, token.user_id)
    if user.email.lower() != token.email.lower():
        raise BadRequestError("Invalid or already-used link.")
    if not user.email_confirmed:
        user.email_confirmed = True
        await session.flush()
    pair = await issue_token_pair(token_service, refresh_store, user)
    logger.info("magic_login_succeeded", extra={"user_id": user.id})
    return pair


# --- password reset -------------------------------------------------------- #


async def request_password_reset(
    session: AsyncSession,
    *,
    email: str,
    settings: Settings,
    clock: Clock = SYSTEM_CLOCK,
) -> str | None:
    """Issue a ``password_reset`` token, or ``None`` if no such user (non-enumerating)."""
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    issued = await issue_token(
        session,
        user_id=user.id,
        email=user.email,
        purpose="password_reset",
        ttl_seconds=settings.password_reset_token_ttl,
        clock=clock,
    )
    return issued.raw


async def complete_password_reset(
    session: AsyncSession,
    refresh_store: RefreshStore,
    hasher: PasswordHasher,
    *,
    raw_token: str,
    new_password: str,
    clock: Clock = SYSTEM_CLOCK,
) -> None:
    """Consume a ``password_reset`` token, set the new password, revoke all sessions.

    Validates the new password (spec-06 rule), confirms the email (the link proves
    inbox ownership) and signs out every existing session (spec 07/08 revocation).
    """
    token = await consume_token(session, raw_token=raw_token, purpose="password_reset", clock=clock)
    user = await _load_user(session, token.user_id)
    _validate_new_password(user, new_password)
    user.hashed_password = await asyncio.to_thread(hasher.hash, new_password)
    if not user.email_confirmed:
        user.email_confirmed = True
    await session.flush()
    await refresh_store.revoke_user(user.id)
    logger.info("password_reset_completed", extra={"user_id": user.id})


# --- internals ------------------------------------------------------------- #


async def _load_user(session: AsyncSession, user_id: object) -> User:
    from inkstave.db.models.user import User

    user = await session.get(User, user_id)
    if user is None:
        # The token's FK is CASCADE, so a consumed token always has a live user;
        # a missing one means the account was deleted mid-flight — treat as invalid.
        raise BadRequestError("Invalid or already-used link.")
    return user
