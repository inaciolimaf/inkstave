"""Account self-management services (spec 59): profile, preferences, password,
email change (token groundwork) and deletion. Endpoints stay thin; the security
rules (re-auth, hashing, single-use tokens, session revocation) live here.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import PasswordHasher
from inkstave.auth.refresh_store import RefreshStore
from inkstave.config import Settings
from inkstave.db.models.user import User
from inkstave.errors import BadRequestError, ConflictError, GoneError, UnauthorizedError
from inkstave.schemas.user import EditorPreferences
from inkstave.services.sharing import generate_token, hash_token
from inkstave.services.user import email_exists, normalise_email
from inkstave.time import SYSTEM_CLOCK, Clock


async def _require_password(hasher: PasswordHasher, user: User, password: str) -> None:
    # Argon2 verify is offloaded so it never blocks the event loop (spec 93).
    if not await asyncio.to_thread(hasher.verify, password, user.hashed_password):
        raise UnauthorizedError("Current password is incorrect.")


async def update_profile(
    session: AsyncSession,
    user: User,
    *,
    display_name: str | None,
    avatar_url: str | None,
    avatar_set: bool,
) -> User:
    """Update the profile in place. ``avatar_set`` distinguishes "clear avatar"
    (explicit null) from "leave unchanged" (field omitted)."""
    if display_name is not None:
        user.display_name = display_name
    if avatar_set:
        user.avatar_url = avatar_url
    await session.flush()
    return user


async def set_editor_preferences(
    session: AsyncSession, user: User, prefs: EditorPreferences
) -> EditorPreferences:
    user.editor_preferences = prefs.model_dump()
    await session.flush()
    return prefs


async def change_password(
    session: AsyncSession,
    refresh_store: RefreshStore,
    hasher: PasswordHasher,
    user: User,
    *,
    current_password: str,
    new_password: str,
) -> None:
    """Re-hash after verifying the current password, then revoke every existing
    refresh token (policy: all sessions sign out — the actor re-authenticates)."""
    await _require_password(hasher, user, current_password)
    if user.email.split("@", 1)[0].lower() in new_password.lower():
        raise BadRequestError("Password must not contain your email address.")
    user.hashed_password = await asyncio.to_thread(hasher.hash, new_password)
    await session.flush()
    await refresh_store.revoke_user(user.id)


async def start_email_change(
    session: AsyncSession,
    hasher: PasswordHasher,
    user: User,
    *,
    new_email: str,
    current_password: str,
    settings: Settings,
    clock: Clock = SYSTEM_CLOCK,
) -> str:
    """Stage an email change and return the raw confirmation token (to be sent to
    the NEW address). The active email is unchanged until confirmation."""
    await _require_password(hasher, user, current_password)
    normalized = normalise_email(new_email)
    if normalized == user.email.lower():
        raise BadRequestError("That is already your email address.")
    if await email_exists(session, normalized):
        raise ConflictError("That email address is already in use.")

    raw_token = generate_token()
    user.pending_email = normalized
    user.email_change_token_hash = hash_token(raw_token)
    user.email_change_expires_at = clock.now() + timedelta(seconds=settings.email_change_token_ttl)
    await session.flush()
    return raw_token


async def confirm_email_change(
    session: AsyncSession, *, token: str, clock: Clock = SYSTEM_CLOCK
) -> User:
    """Swap email ← pending_email if the (single-use, unexpired) token matches."""
    token_hash = hash_token(token)
    user = await session.scalar(select(User).where(User.email_change_token_hash == token_hash))
    if user is None or user.pending_email is None:
        raise BadRequestError("Invalid or already-used confirmation token.")
    if user.email_change_expires_at is None or user.email_change_expires_at < clock.now():
        # A flush here would be rolled back along with the GoneError, so don't
        # pretend to clear: the stale pending fields are harmless and are
        # overwritten the next time the user starts an email change.
        raise GoneError("This confirmation link has expired.")

    user.email = user.pending_email
    user.email_confirmed = True
    _clear_email_change(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        # The address was taken between request and confirmation.
        raise ConflictError("That email address is already in use.") from exc
    return user


def _clear_email_change(user: User) -> None:
    user.pending_email = None
    user.email_change_token_hash = None
    user.email_change_expires_at = None


async def delete_account(
    session: AsyncSession,
    refresh_store: RefreshStore,
    hasher: PasswordHasher,
    user: User,
    *,
    password: str,
) -> None:
    """Hard-delete the account after re-auth. Owned projects (and their files,
    history, memberships, invites) cascade away via the DB FKs; all sessions are
    revoked. See docs/adr/0059."""
    await _require_password(hasher, user, password)
    user_id = user.id
    await session.delete(user)
    await session.flush()
    # Revoke after the delete succeeds: a failed delete rolls back without having
    # killed sessions; once the row is gone every auth lookup fails anyway.
    await refresh_store.revoke_user(user_id)
