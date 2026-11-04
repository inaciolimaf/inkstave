"""Comment thread routes (spec 118). HTTP only: the service holds the rules, the publisher the events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.errors import ErrorEnvelope
from inkstave.modules.auth import get_current_user, rate_limit_named
from inkstave.modules.discussion.comments.publish import CommentPublisher, get_comment_publisher
from inkstave.modules.discussion.comments.schemas import (
    CommentMessageRead,
    CommentMessageWrite,
    CommentThreadCreate,
    CommentThreadList,
    CommentThreadRead,
)
from inkstave.modules.discussion.comments.service import CommentService
from inkstave.modules.projects import Capability, require_capability

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.modules.auth import User
    from inkstave.modules.projects import Project

router = APIRouter(prefix="/projects/{project_id}/comments", tags=["comments"])

_ERRORS: dict[int | str, dict[str, Any]] = {404: {"model": ErrorEnvelope}}
_READ = Depends(require_capability(Capability.PROJECT_READ))
_WRITE = Depends(require_capability(Capability.DISCUSSION_WRITE))
_PROJECT = Depends(require_capability(Capability.DISCUSSION_WRITE))
_LIMITED = Depends(rate_limit_named("comments"))


@router.get(
    "",
    response_model=CommentThreadList,
    summary="Comment threads of a project, or of one document",
    responses=_ERRORS,
    dependencies=[_READ],
)
async def list_threads(
    project_id: UUID,
    document_id: UUID | None = Query(None, description="Only the threads of this document"),
    status_filter: Literal["open", "resolved", "all"] = Query("all", alias="status"),
    session: AsyncSession = UNIT_OF_WORK,
) -> CommentThreadList:
    items = await CommentService(session).list_threads(
        project_id, document_id=document_id, status=status_filter
    )
    return CommentThreadList(items=items)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentThreadRead,
    summary="Start a comment thread on a passage",
    responses=_ERRORS,
    dependencies=[_LIMITED],
)
async def create_thread(
    payload: CommentThreadCreate,
    project: Project = _PROJECT,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    publisher: CommentPublisher = Depends(get_comment_publisher),
) -> CommentThreadRead:
    outcome = await CommentService(session).create_thread(project, user, payload)
    return publisher.emit(project.id, outcome)


@router.post(
    "/{thread_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentMessageRead,
    summary="Reply in a thread",
    responses=_ERRORS,
    dependencies=[_LIMITED],
)
async def add_reply(
    thread_id: UUID,
    payload: CommentMessageWrite,
    project: Project = _PROJECT,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    publisher: CommentPublisher = Depends(get_comment_publisher),
) -> CommentMessageRead:
    outcome = await CommentService(session).add_reply(project, user, thread_id, payload)
    return publisher.emit(project.id, outcome)


@router.patch(
    "/{thread_id}/messages/{message_id}",
    response_model=CommentMessageRead,
    summary="Edit your own message",
    responses=_ERRORS,
    dependencies=[_WRITE],
)
async def edit_message(
    thread_id: UUID,
    message_id: UUID,
    payload: CommentMessageWrite,
    project: Project = _PROJECT,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    publisher: CommentPublisher = Depends(get_comment_publisher),
) -> CommentMessageRead:
    outcome = await CommentService(session).edit_message(project, user, thread_id, message_id, payload)
    return publisher.emit(project.id, outcome)


@router.delete(
    "/{thread_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your own message; the last one deletes the thread",
    responses=_ERRORS,
    dependencies=[_WRITE],
)
async def delete_message(
    thread_id: UUID,
    message_id: UUID,
    project: Project = _PROJECT,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    publisher: CommentPublisher = Depends(get_comment_publisher),
) -> None:
    outcome = await CommentService(session).delete_message(project.id, user.id, thread_id, message_id)
    publisher.emit(project.id, outcome)


@router.post(
    "/{thread_id}/resolve",
    response_model=CommentThreadRead,
    summary="Resolve a thread",
    responses=_ERRORS,
    dependencies=[_WRITE],
)
async def resolve_thread(
    thread_id: UUID,
    project: Project = _PROJECT,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    publisher: CommentPublisher = Depends(get_comment_publisher),
) -> CommentThreadRead:
    outcome = await CommentService(session).set_resolved(project.id, user, thread_id, resolved=True)
    return publisher.emit(project.id, outcome)


@router.post(
    "/{thread_id}/reopen",
    response_model=CommentThreadRead,
    summary="Reopen a resolved thread",
    responses=_ERRORS,
    dependencies=[_WRITE],
)
async def reopen_thread(
    thread_id: UUID,
    project: Project = _PROJECT,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    publisher: CommentPublisher = Depends(get_comment_publisher),
) -> CommentThreadRead:
    outcome = await CommentService(session).set_resolved(project.id, user, thread_id, resolved=False)
    return publisher.emit(project.id, outcome)
