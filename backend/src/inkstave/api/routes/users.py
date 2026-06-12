"""User-facing routes. Spec 08 adds the authenticated ``/users/me`` proof."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from inkstave.auth.dependencies import get_current_user
from inkstave.db.models.user import User
from inkstave.errors import ErrorEnvelope
from inkstave.schemas.user import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Return the authenticated user",
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope}},
)
async def read_me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)
