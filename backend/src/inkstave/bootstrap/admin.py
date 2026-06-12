"""Idempotent, race-safe first-admin bootstrap (spec 57).

``ensure_initial_admin`` creates exactly the **first** admin and is a no-op once
one exists. Concurrent callers serialize on a transaction-scoped advisory lock, so
two simultaneous ``POST /api/setup/admin`` requests can never create two admins.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import PasswordHasher
from inkstave.db.models.user import User
from inkstave.services.user import normalise_email

logger = logging.getLogger("inkstave.bootstrap")

# Transaction-scoped advisory key — serializes concurrent first-admin creation.
_ADMIN_LOCK_KEY = 0x41444D4E  # "ADMN"


async def admin_exists(session: AsyncSession) -> bool:
    """True if any user already carries the admin flag."""
    count = await session.scalar(
        select(func.count()).select_from(User).where(User.is_admin.is_(True))
    )
    return bool(count)


async def ensure_initial_admin(
    session: AsyncSession,
    hasher: PasswordHasher,
    *,
    email: str,
    password: str,
    display_name: str,
) -> User | None:
    """Create the first admin if none exists; otherwise return ``None`` (no-op).

    Caller owns the transaction (commit/rollback). The advisory lock is released
    automatically at transaction end, so the serialization is leak-free.
    """
    # Serialize concurrent callers: the second waits here, then sees the admin.
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADMIN_LOCK_KEY})
    if await admin_exists(session):
        return None

    user = User(
        email=normalise_email(email),
        hashed_password=hasher.hash(password),
        display_name=display_name.strip(),
        is_admin=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    logger.info("Created initial admin %s", user.email)
    return user
