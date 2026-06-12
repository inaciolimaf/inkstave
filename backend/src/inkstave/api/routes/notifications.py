"""In-app notification routes (spec 39). Per-user; JWT-authenticated."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from inkstave.auth.dependencies import get_current_user
from inkstave.db.session import get_db_session
from inkstave.errors import ErrorEnvelope
from inkstave.notifications.service import NotificationService
from inkstave.schemas.notification import (
    MarkAllResult,
    NotificationList,
    NotificationRead,
    UnreadCount,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.db.models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}


@router.get("", response_model=NotificationList, summary="List active notifications")
async def list_notifications(
    before: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> NotificationList:
    service = NotificationService(session)
    items = await service.list_active(user_id=user.id, limit=limit, before=before)
    return NotificationList(
        items=[NotificationRead.model_validate(n) for n in items],
        unread_count=await service.unread_count(user_id=user.id),
    )


@router.get("/unread-count", response_model=UnreadCount, summary="Unread notification count")
async def get_unread_count(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UnreadCount:
    return UnreadCount(count=await NotificationService(session).unread_count(user_id=user.id))


@router.post("/{notification_id}/read", response_model=NotificationRead, responses=_NOT_FOUND)
async def mark_read(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> NotificationRead:
    notification = await NotificationService(session).mark_read(
        user_id=user.id, notification_id=notification_id
    )
    return NotificationRead.model_validate(notification)


@router.post("/read-all", response_model=MarkAllResult, summary="Mark all read")
async def mark_all_read(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MarkAllResult:
    return MarkAllResult(updated=await NotificationService(session).mark_all_read(user_id=user.id))


@router.delete(
    "/{notification_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND
)
async def dismiss(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await NotificationService(session).dismiss(user_id=user.id, notification_id=notification_id)
