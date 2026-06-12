"""User account routes: the authenticated ``/users/me`` profile (spec 08) plus
self-service settings — profile, editor preferences, password, email change and
account deletion (spec 59). All ``/me`` routes require the current user; the
token-authorized ``confirm-email-change`` is intentionally unauthenticated.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.dependencies import get_current_user, get_optional_user
from inkstave.auth.password import PasswordHasher
from inkstave.auth.refresh_store import RefreshStore
from inkstave.config import Settings
from inkstave.db.models.user import User
from inkstave.db.session import get_db_session
from inkstave.dependencies import (
    get_email_enqueuer,
    get_password_hasher,
    get_redis,
    get_refresh_store,
    get_settings_dep,
)
from inkstave.errors import ErrorEnvelope, RateLimitError
from inkstave.mailer.enqueuer import EmailEnqueuer
from inkstave.schemas.auth import MessageResponse
from inkstave.schemas.user import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    ConfirmEmailChangeRequest,
    DeleteAccountRequest,
    EditorPreferences,
    UpdateProfileRequest,
    UserMe,
)
from inkstave.security.rate_limit import check_rate_limit, policy_from_setting
from inkstave.services import account

router = APIRouter(prefix="/users", tags=["users"])

_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope}
}


def _auth_password_rate_limit() -> Any:
    """Rate-limit dependency for sensitive password endpoints (spec 52 §5.2.1;
    spec 68 #217): ``RATE_LIMIT_AUTH_PASSWORD`` (default 5/hour), keyed by
    ``user_or_ip`` so an authenticated actor is limited per-user. Reads the limit
    from settings at request time and respects ``RATE_LIMIT_ENABLED``."""

    async def dependency(
        request: Request,
        user: User | None = Depends(get_optional_user),
        redis: Any = Depends(get_redis),
        settings: Settings = Depends(get_settings_dep),
    ) -> None:
        if not settings.rate_limit_enabled:
            return
        policy = policy_from_setting(
            "auth_password", settings.rate_limit_auth_password, "user_or_ip"
        )
        scope_id = (
            f"user:{user.id}"
            if user is not None
            else f"ip:{request.client.host if request.client else 'unknown'}"
        )
        try:
            result = await check_rate_limit(redis, policy, scope_id, now=time.time())
        except Exception:
            return  # fail open: a limiter outage must not lock out legitimate traffic
        if not result.allowed:
            raise RateLimitError(
                result.retry_after, limit=result.limit, remaining=0, reset=result.reset
            )

    # Marker so the spec-55 guard-coverage audit detects the policy on the route.
    dependency.__rate_limit__ = "auth_password"  # type: ignore[attr-defined]
    return dependency


# NOTE (spec 68 #22): spec 08 originally prescribed ``UserPublic`` for ``GET /me``;
# spec 59 upgraded it to ``UserMe`` (a strict superset adding avatar_url,
# editor_preferences, pending_email). The response model is intentionally the
# superset — no consumer of UserPublic breaks. Do not downgrade it.
@router.get("/me", response_model=UserMe, summary="The authenticated user", responses=_UNAUTHORIZED)
async def read_me(user: User = Depends(get_current_user)) -> UserMe:
    return UserMe.model_validate(user)


@router.patch("/me", response_model=UserMe, summary="Update profile", responses=_UNAUTHORIZED)
async def update_me(
    data: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserMe:
    updated = await account.update_profile(
        session,
        user,
        display_name=data.display_name,
        avatar_url=data.avatar_url,
        avatar_set="avatar_url" in data.model_fields_set,
    )
    return UserMe.model_validate(updated)


@router.put(
    "/me/editor-preferences",
    response_model=EditorPreferences,
    summary="Set editor preferences",
    responses=_UNAUTHORIZED,
)
async def put_editor_preferences(
    prefs: EditorPreferences,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EditorPreferences:
    return await account.set_editor_preferences(session, user, prefs)


@router.post(
    "/me/change-password",
    response_model=MessageResponse,
    summary="Change password (signs out other sessions)",
    dependencies=[Depends(_auth_password_rate_limit())],
    responses=_UNAUTHORIZED,
)
async def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    hasher: PasswordHasher = Depends(get_password_hasher),
    refresh_store: RefreshStore = Depends(get_refresh_store),
) -> MessageResponse:
    await account.change_password(
        session,
        refresh_store,
        hasher,
        user,
        current_password=data.current_password,
        new_password=data.new_password,
    )
    return MessageResponse(detail="Password changed. Other sessions were signed out.")


@router.post(
    "/me/change-email",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an email change (confirmation sent to the new address)",
    responses=_UNAUTHORIZED,
)
async def change_email(
    data: ChangeEmailRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    hasher: PasswordHasher = Depends(get_password_hasher),
    settings: Settings = Depends(get_settings_dep),
    emails: EmailEnqueuer = Depends(get_email_enqueuer),
) -> MessageResponse:
    raw_token = await account.start_email_change(
        session,
        hasher,
        user,
        new_email=str(data.new_email),
        current_password=data.current_password,
        settings=settings,
    )
    confirm_url = f"{settings.frontend_url}/settings/confirm-email?token={raw_token}"
    await emails.enqueue_email(
        template="email_change_confirmation",
        to=str(data.new_email),
        context={"user_name": user.display_name, "confirm_url": confirm_url},
    )
    return MessageResponse(detail=f"Confirmation sent to {data.new_email}.")


@router.post(
    "/confirm-email-change",
    response_model=UserMe,
    summary="Confirm an email change via its token (unauthenticated)",
)
async def confirm_email_change(
    data: ConfirmEmailChangeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> UserMe:
    user = await account.confirm_email_change(session, token=data.token)
    return UserMe.model_validate(user)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the account (hard delete; cascades owned projects)",
    responses=_UNAUTHORIZED,
)
async def delete_me(
    data: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    hasher: PasswordHasher = Depends(get_password_hasher),
    refresh_store: RefreshStore = Depends(get_refresh_store),
) -> Response:
    await account.delete_account(session, refresh_store, hasher, user, password=data.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
