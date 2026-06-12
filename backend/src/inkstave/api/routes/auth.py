"""Authentication routes: registration (spec 06) and login/refresh/logout (07)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, status

from inkstave.auth.password import PasswordHasher
from inkstave.auth.rate_limit import rate_limit
from inkstave.auth.refresh_store import RefreshStore
from inkstave.auth.tokens import TokenService
from inkstave.db.session import get_db_session
from inkstave.dependencies import (
    get_password_hasher,
    get_refresh_store,
    get_token_service,
)
from inkstave.errors import ErrorEnvelope
from inkstave.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    TokenPair,
)
from inkstave.schemas.user import RegisterRequest, UserPublic
from inkstave.services import auth as auth_service
from inkstave.services.user import register_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope}
}


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserPublic,
    summary="Register a new account",
    dependencies=[Depends(rate_limit("register"))],
    responses={status.HTTP_409_CONFLICT: {"model": ErrorEnvelope}},
)
async def register(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    hasher: PasswordHasher = Depends(get_password_hasher),
) -> UserPublic:
    """Create an account from an email, password and display name."""
    user = await register_user(session, hasher, data)
    return UserPublic.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Log in and receive an access + refresh token pair",
    dependencies=[Depends(rate_limit("login"))],
    responses=_UNAUTHORIZED,
)
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
    hasher: PasswordHasher = Depends(get_password_hasher),
    token_service: TokenService = Depends(get_token_service),
    refresh_store: RefreshStore = Depends(get_refresh_store),
) -> TokenPair:
    """Authenticate credentials and issue a new token family."""
    return await auth_service.login(session, hasher, token_service, refresh_store, data)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a refresh token for a new access + refresh pair",
    dependencies=[Depends(rate_limit("refresh"))],
    responses=_UNAUTHORIZED,
)
async def refresh(
    data: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
    token_service: TokenService = Depends(get_token_service),
    refresh_store: RefreshStore = Depends(get_refresh_store),
) -> TokenPair:
    """Rotate the presented refresh token; detect and punish reuse."""
    return await auth_service.refresh_tokens(
        session, token_service, refresh_store, data.refresh_token
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke a refresh token (and its family)",
)
async def logout(
    data: LogoutRequest,
    token_service: TokenService = Depends(get_token_service),
    refresh_store: RefreshStore = Depends(get_refresh_store),
) -> MessageResponse:
    """Idempotently revoke the token's family; unknown tokens still return 200."""
    await auth_service.logout(token_service, refresh_store, data.refresh_token)
    return MessageResponse(detail="Logged out.")
