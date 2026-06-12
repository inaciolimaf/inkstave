"""Authentication service: login, refresh (with rotation + reuse detection),
and logout. Routers stay thin; all token/credential logic lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select

from inkstave.auth.tokens import TokenError
from inkstave.db.models.user import User
from inkstave.errors import UnauthorizedError
from inkstave.schemas.auth import TokenPair
from inkstave.services.user import normalise_email

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.auth.password import PasswordHasher
    from inkstave.auth.refresh_store import RefreshStore
    from inkstave.auth.tokens import TokenService
    from inkstave.schemas.auth import LoginRequest

# A fixed valid argon2id hash. When the email is unknown we still run a verify
# against this dummy so the response timing does not reveal user existence.
_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$cF5MiWJGhHDA671dONGDCQ$"
    "YQw+PB8wiO1F5J5FKpXwV2abCar+N5OwX9W6/SmiqmE"
)

_INVALID_CREDENTIALS = "Invalid email or password."
_INVALID_REFRESH = "Invalid or expired refresh token."
_REUSE_DETECTED = "Refresh token reuse detected; session revoked."


class InvalidCredentialsError(UnauthorizedError):
    """Raised on a bad email or password (uniform, non-enumerating)."""

    def __init__(self) -> None:
        super().__init__(_INVALID_CREDENTIALS)


class RefreshError(UnauthorizedError):
    """Raised when a refresh token is missing, expired, reused, or revoked."""


async def authenticate_user(
    session: AsyncSession, hasher: PasswordHasher, email: str, password: str
) -> User | None:
    """Return the user for valid credentials, else ``None`` (constant-time)."""
    normalised = normalise_email(email)
    user = (
        await session.execute(select(User).where(User.email == normalised))
    ).scalar_one_or_none()

    if user is None:
        # Spend comparable time so a missing user is not faster than a wrong one.
        hasher.verify(password, _DUMMY_HASH)
        return None
    if not hasher.verify(password, user.hashed_password):
        return None
    return user


async def login(
    session: AsyncSession,
    hasher: PasswordHasher,
    token_service: TokenService,
    refresh_store: RefreshStore,
    data: LoginRequest,
) -> TokenPair:
    user = await authenticate_user(session, hasher, data.email, data.password)
    if user is None:
        raise InvalidCredentialsError()

    family_id = uuid4()
    access_token, expires_in = token_service.create_access_token(user)
    refresh_token, jti = token_service.create_refresh_token(user.id, family_id)
    await refresh_store.store_refresh(jti, user.id, family_id)
    return TokenPair(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)


async def refresh_tokens(
    session: AsyncSession,
    token_service: TokenService,
    refresh_store: RefreshStore,
    refresh_token: str,
) -> TokenPair:
    try:
        claims = token_service.decode_token(refresh_token, "refresh")
    except TokenError as exc:
        raise RefreshError(_INVALID_REFRESH) from exc

    jti = claims["jti"]
    family_id = claims["family_id"]

    record = await refresh_store.get_refresh(jti)
    if record is None or await refresh_store.is_family_revoked(family_id):
        raise RefreshError(_INVALID_REFRESH)
    if record.rotated:
        # Replay of an already-used token -> revoke the entire family.
        await refresh_store.revoke_family(family_id)
        raise RefreshError(_REUSE_DETECTED)
    # Per-user cutoff: a password change (spec 59) invalidates tokens issued before it.
    if await refresh_store.is_user_revoked(record):
        raise RefreshError(_INVALID_REFRESH)

    user = await session.get(User, UUID(claims["sub"]))
    if user is None:
        raise RefreshError(_INVALID_REFRESH)

    await refresh_store.rotate_refresh(jti)
    access_token, expires_in = token_service.create_access_token(user)
    new_refresh, new_jti = token_service.create_refresh_token(user.id, UUID(family_id))
    await refresh_store.store_refresh(new_jti, user.id, UUID(family_id))
    return TokenPair(access_token=access_token, refresh_token=new_refresh, expires_in=expires_in)


async def logout(
    token_service: TokenService, refresh_store: RefreshStore, refresh_token: str
) -> None:
    """Revoke the token's family. Idempotent: invalid tokens are a no-op."""
    try:
        claims = token_service.decode_token(refresh_token, "refresh")
    except TokenError:
        return
    await refresh_store.revoke_family(claims["family_id"])
