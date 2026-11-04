"""Project chat routes (spec 117). HTTP only: the service holds the logic and the SQL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.deps import get_redis
from inkstave.core.errors import ErrorEnvelope
from inkstave.modules.auth import get_current_user, rate_limit_named
from inkstave.modules.discussion.chat.service import ChatService
from inkstave.modules.discussion.events.channel import schedule_project_event
from inkstave.modules.discussion.schemas import (
    ChatMessageCreate,
    ChatMessagePage,
    ChatMessageRead,
    UnreadCount,
)
from inkstave.modules.projects import Capability, require_capability

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.modules.auth import User

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])

_ERRORS: dict[int | str, dict[str, Any]] = {404: {"model": ErrorEnvelope}}
_READ = Depends(require_capability(Capability.PROJECT_READ))
_WRITE = Depends(require_capability(Capability.DISCUSSION_WRITE))


@router.get(
    "/messages",
    response_model=ChatMessagePage,
    summary="Page of chat messages, newest first",
    responses=_ERRORS,
    dependencies=[_READ],
)
async def list_messages(
    project_id: UUID,
    before: UUID | None = Query(None, description="Id of the oldest message already shown"),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = UNIT_OF_WORK,
) -> ChatMessagePage:
    return await ChatService(session).list_messages(project_id, before=before, limit=limit)


@router.post(
    "/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatMessageRead,
    summary="Post a chat message",
    responses=_ERRORS,
    dependencies=[_WRITE, Depends(rate_limit_named("chat"))],
)
async def post_message(
    project_id: UUID,
    payload: ChatMessageCreate,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    redis: Redis = Depends(get_redis),
) -> ChatMessageRead:
    message = await ChatService(session).create_message(project_id, user, payload.body)
    schedule_project_event(
        background, redis, project_id, "chat.message_created", message.model_dump(mode="json")
    )
    return message


@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your own chat message",
    responses=_ERRORS,
    dependencies=[_WRITE],
)
async def delete_message(
    project_id: UUID,
    message_id: UUID,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    redis: Redis = Depends(get_redis),
) -> None:
    if await ChatService(session).delete_message(project_id, message_id, user.id):
        schedule_project_event(background, redis, project_id, "chat.message_deleted", {"id": str(message_id)})


@router.get(
    "/unread",
    response_model=UnreadCount,
    summary="Messages from others since the chat was last opened",
    responses=_ERRORS,
    dependencies=[_READ],
)
async def unread_count(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> UnreadCount:
    return UnreadCount(count=await ChatService(session).unread_count(project_id, user.id))


@router.post(
    "/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark the chat as read now",
    responses=_ERRORS,
    dependencies=[_READ],
)
async def mark_read(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> None:
    await ChatService(session).mark_read(project_id, user.id)
