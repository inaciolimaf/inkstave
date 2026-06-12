"""User service: registration logic, kept out of the router.

Normalises the email, hashes the password, inserts the user, and translates a
unique-constraint race into a domain error the global handler maps to 409.
The session is committed by the ``get_db_session`` dependency, not here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from inkstave.db.models.user import User
from inkstave.errors import ConflictError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.auth.password import PasswordHasher
    from inkstave.schemas.user import RegisterRequest

logger = logging.getLogger(__name__)


class EmailAlreadyExistsError(ConflictError):
    """Raised when registering an email that is already taken."""

    def __init__(self) -> None:
        super().__init__("An account with this email already exists.")


def normalise_email(email: str) -> str:
    """Trim and lower-case an email for storage and comparison."""
    return email.strip().lower()


async def email_exists(session: AsyncSession, email: str) -> bool:
    """Return whether a user with ``email`` already exists (case-insensitive)."""
    result = await session.execute(select(User.id).where(User.email == email))
    return result.first() is not None


async def register_user(
    session: AsyncSession, hasher: PasswordHasher, data: RegisterRequest
) -> User:
    """Create and persist a new user, or raise :class:`EmailAlreadyExistsError`."""
    email = normalise_email(data.email)
    if await email_exists(session, email):
        # Event only — never the attempted email or password.
        logger.warning("registration rejected: email already exists")
        raise EmailAlreadyExistsError()

    # Argon2 hashing is intentionally expensive — run it off the event loop.
    hashed_password = await asyncio.to_thread(hasher.hash, data.password)
    user = User(
        email=email,
        hashed_password=hashed_password,
        display_name=data.display_name,
    )
    session.add(user)
    try:
        # Flush now so a unique-violation race surfaces here (not at commit) and
        # the server-side defaults are populated for the response.
        await session.flush()
    except IntegrityError as exc:
        logger.warning("registration rejected: email already exists")
        raise EmailAlreadyExistsError() from exc
    await session.refresh(user)
    logger.info("user registered", extra={"user_id": user.id})
    return user
