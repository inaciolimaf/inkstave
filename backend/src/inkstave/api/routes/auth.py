"""Authentication routes: registration (spec 06), login/refresh/logout (07), and
the email link-based account flows — verify / magic-link / reset (spec 104)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, status

from inkstave.auth.password import PasswordHasher
from inkstave.auth.rate_limit import rate_limit
from inkstave.auth.refresh_store import RefreshStore
from inkstave.auth.tokens import TokenService
from inkstave.db.session import get_db_session
from inkstave.dependencies import (
    get_email_enqueuer,
    get_password_hasher,
    get_refresh_store,
    get_settings_dep,
    get_token_service,
)
from inkstave.errors import ErrorEnvelope
from inkstave.mailer.enqueuer import EmailEnqueuer
from inkstave.schemas.auth import (
    EmailOnlyRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenOnlyRequest,
    TokenPair,
)
from inkstave.schemas.user import RegisterRequest, UserPublic
from inkstave.services import auth as auth_service
from inkstave.services import email_auth
from inkstave.services.user import get_user_by_email, register_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope}
}

# Standard 400/410 envelope set for the token-consuming callback endpoints.
_CALLBACK_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorEnvelope},
    status.HTTP_410_GONE: {"model": ErrorEnvelope},
}

# Identical, non-enumerating responses for the three request endpoints.
_LINK_ON_ITS_WAY = "If that email is registered, a link is on its way."
_RESET_ON_ITS_WAY = "If that email is registered, a reset link is on its way."


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
    settings: Settings = Depends(get_settings_dep),
    emails: EmailEnqueuer = Depends(get_email_enqueuer),
) -> UserPublic:
    """Create an account from an email, password and display name."""
    user = await register_user(session, hasher, data)
    # Fire-and-forget account verification email — never blocks the response; the
    # actual send happens in the ARQ send_email_job. The link now carries a real
    # persisted ``email_verify`` token (spec 104 replaces 103's throwaway token).
    raw = await email_auth.request_email_verification(session, user, settings=settings)
    verify_url = f"{settings.frontend_url}/verify-email?token={raw}"
    await emails.enqueue_email(
        template="email_verification",
        to=user.email,
        context={"user_name": user.display_name, "verify_url": verify_url},
    )
    return UserPublic.model_validate(user)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
    summary="Request a password-reset email",
    dependencies=[Depends(rate_limit("forgot_password"))],
)
async def forgot_password(
    data: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    emails: EmailEnqueuer = Depends(get_email_enqueuer),
) -> MessageResponse:
    """Send a password-reset link — non-enumerating (same response either way).

    Only enqueues the email when a matching user exists; the response is identical
    whether or not the address is registered, so it can't be used to probe accounts.
    The link now carries a real persisted token (spec 104 owns this flow).
    """
    raw = await email_auth.request_password_reset(session, email=str(data.email), settings=settings)
    if raw is not None:
        user = await get_user_by_email(session, str(data.email))
        assert user is not None  # raw is only non-None when the user exists
        reset_url = f"{settings.frontend_url}/reset-password?token={raw}"
        await emails.enqueue_email(
            template="password_reset",
            to=user.email,
            context={"user_name": user.display_name, "reset_url": reset_url},
        )
    return MessageResponse(detail=_RESET_ON_ITS_WAY)


@router.post(
    "/verify-email/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
    summary="Resend the account-verification email",
    dependencies=[Depends(rate_limit("verify_email"))],
)
async def resend_verification(
    data: EmailOnlyRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    emails: EmailEnqueuer = Depends(get_email_enqueuer),
) -> MessageResponse:
    """Re-send the verification link — non-enumerating, enqueues at most one job.

    Only enqueues when the user exists **and is not yet confirmed**; confirmed or
    unknown addresses silently get nothing but the identical 202 (no spam, no
    enumeration).
    """
    user = await get_user_by_email(session, str(data.email))
    if user is not None and not user.email_confirmed:
        raw = await email_auth.request_email_verification(session, user, settings=settings)
        verify_url = f"{settings.frontend_url}/verify-email?token={raw}"
        await emails.enqueue_email(
            template="email_verification",
            to=user.email,
            context={"user_name": user.display_name, "verify_url": verify_url},
        )
    return MessageResponse(detail=_LINK_ON_ITS_WAY)


@router.post(
    "/verify-email/confirm",
    response_model=UserPublic,
    summary="Confirm an account email from a verification link",
    dependencies=[Depends(rate_limit("verify_email"))],
    responses=_CALLBACK_ERRORS,
)
async def confirm_verification(
    data: TokenOnlyRequest,
    session: AsyncSession = Depends(get_db_session),
) -> UserPublic:
    """Consume the verification token and set ``email_confirmed`` (idempotent)."""
    user = await email_auth.confirm_email_verification(session, raw_token=data.token)
    return UserPublic.model_validate(user)


@router.post(
    "/magic-link",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
    summary="Request a passwordless sign-in link",
    dependencies=[Depends(rate_limit("magic_link"))],
)
async def magic_link(
    data: EmailOnlyRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    emails: EmailEnqueuer = Depends(get_email_enqueuer),
) -> MessageResponse:
    """Send a one-time sign-in link — non-enumerating; enqueues only if the user exists."""
    raw = await email_auth.request_magic_login(session, email=str(data.email), settings=settings)
    if raw is not None:
        user = await get_user_by_email(session, str(data.email))
        assert user is not None
        magic_url = f"{settings.frontend_url}/magic-link?token={raw}"
        await emails.enqueue_email(
            template="magic_login",
            to=user.email,
            context={"user_name": user.display_name, "magic_url": magic_url},
        )
    return MessageResponse(detail=_LINK_ON_ITS_WAY)


@router.post(
    "/magic-link/callback",
    response_model=TokenPair,
    summary="Complete a passwordless sign-in and receive a token pair",
    dependencies=[Depends(rate_limit("magic_link"))],
    responses=_CALLBACK_ERRORS,
)
async def magic_link_callback(
    data: TokenOnlyRequest,
    session: AsyncSession = Depends(get_db_session),
    token_service: TokenService = Depends(get_token_service),
    refresh_store: RefreshStore = Depends(get_refresh_store),
) -> TokenPair:
    """Consume the magic-link token and issue the real JWT access+refresh pair."""
    return await email_auth.complete_magic_login(
        session, token_service, refresh_store, raw_token=data.token
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Set a new password from a reset link (revokes all sessions)",
    dependencies=[Depends(rate_limit("reset_password"))],
    responses=_CALLBACK_ERRORS,
)
async def reset_password(
    data: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
    hasher: PasswordHasher = Depends(get_password_hasher),
    refresh_store: RefreshStore = Depends(get_refresh_store),
) -> MessageResponse:
    """Consume the reset token, set the new password, confirm email, sign out all sessions."""
    await email_auth.complete_password_reset(
        session,
        refresh_store,
        hasher,
        raw_token=data.token,
        new_password=data.new_password,
    )
    return MessageResponse(detail="Password updated — please sign in.")


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
    settings: Settings = Depends(get_settings_dep),
) -> TokenPair:
    """Authenticate credentials and issue a new token family.

    When ``require_verified_email_to_login`` is on (spec 104), an unconfirmed user
    is rejected; the magic-link / reset flows still let them in (they confirm).
    """
    return await auth_service.login(
        session,
        hasher,
        token_service,
        refresh_store,
        data,
        require_verified_email=settings.require_verified_email_to_login,
    )


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
