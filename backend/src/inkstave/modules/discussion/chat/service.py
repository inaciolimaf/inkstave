"""The project chat: paging, posting, soft delete and the unread count (spec 117).

The service never commits. The request's unit of work does, and the routes publish the
live event only after that commit (see ``events/publish.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from inkstave.modules.auth import User
from inkstave.modules.discussion.errors import ChatMessageNotFoundError, NotMessageAuthorError
from inkstave.modules.discussion.models import ProjectChatMessage, ProjectChatRead
from inkstave.modules.discussion.schemas import ChatAuthor, ChatMessagePage, ChatMessageRead

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _author(user: User | None) -> ChatAuthor | None:
    return ChatAuthor(id=user.id, display_name=user.display_name) if user is not None else None


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_messages(self, project_id: UUID, *, before: UUID | None, limit: int) -> ChatMessagePage:
        """The newest ``limit`` messages older than ``before`` (the cursor is a message id)."""
        cursor = await self._cursor(project_id, before)
        statement = self._page_statement(project_id, cursor).limit(limit + 1)
        rows = list((await self._session.execute(statement)).all())
        has_more = len(rows) > limit
        items = [ChatMessageRead.from_message(message, _author(author)) for message, author in rows[:limit]]
        return ChatMessagePage(items=items, has_more=has_more)

    async def _cursor(self, project_id: UUID, before: UUID | None) -> ProjectChatMessage | None:
        if before is None:
            return None
        anchor = await self._session.get(ProjectChatMessage, before)
        if anchor is None or anchor.project_id != project_id:
            raise ChatMessageNotFoundError()
        return anchor

    @staticmethod
    def _page_statement(
        project_id: UUID, cursor: ProjectChatMessage | None
    ) -> Select[tuple[ProjectChatMessage, User]]:
        statement = (
            select(ProjectChatMessage, User)
            .outerjoin(User, User.id == ProjectChatMessage.author_id)
            .where(ProjectChatMessage.project_id == project_id)
            .order_by(ProjectChatMessage.created_at.desc(), ProjectChatMessage.id.desc())
        )
        if cursor is not None:
            # Strictly before the cursor in (created_at, id) order, written out so mypy and the planner agree.
            older = or_(
                ProjectChatMessage.created_at < cursor.created_at,
                and_(
                    ProjectChatMessage.created_at == cursor.created_at,
                    ProjectChatMessage.id < cursor.id,
                ),
            )
            statement = statement.where(older)
        return statement

    async def create_message(self, project_id: UUID, author: User, body: str) -> ChatMessageRead:
        # Wall-clock time, not now(): every statement of one transaction shares now(), which would
        # give a message and a read made in the same transaction the same timestamp.
        message = ProjectChatMessage(
            project_id=project_id, author_id=author.id, body=body, created_at=datetime.now(UTC)
        )
        self._session.add(message)
        await self._session.flush()
        return ChatMessageRead.from_message(message, _author(author))

    async def delete_message(self, project_id: UUID, message_id: UUID, user_id: UUID) -> bool:
        """Soft-delete an own message. Returns False when it was already deleted."""
        message = await self._session.get(ProjectChatMessage, message_id)
        if message is None or message.project_id != project_id:
            raise ChatMessageNotFoundError()
        if message.author_id != user_id:
            raise NotMessageAuthorError()
        if message.deleted_at is not None:
            return False
        message.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def unread_count(self, project_id: UUID, user_id: UUID) -> int:
        """Messages from others, not deleted, posted since the user last opened the chat."""
        last_read = await self._last_read(project_id, user_id)
        statement = (
            select(func.count())
            .select_from(ProjectChatMessage)
            .where(
                ProjectChatMessage.project_id == project_id,
                ProjectChatMessage.deleted_at.is_(None),
                ProjectChatMessage.author_id.is_distinct_from(user_id),
            )
        )
        if last_read is not None:
            statement = statement.where(ProjectChatMessage.created_at > last_read)
        return int((await self._session.execute(statement)).scalar_one())

    async def _last_read(self, project_id: UUID, user_id: UUID) -> datetime | None:
        statement = select(ProjectChatRead.last_read_at).where(
            ProjectChatRead.project_id == project_id, ProjectChatRead.user_id == user_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def mark_read(self, project_id: UUID, user_id: UUID) -> None:
        insert = pg_insert(ProjectChatRead).values(
            project_id=project_id, user_id=user_id, last_read_at=func.clock_timestamp()
        )
        statement = insert.on_conflict_do_update(
            index_elements=[ProjectChatRead.project_id, ProjectChatRead.user_id],
            set_={"last_read_at": func.clock_timestamp()},
        )
        await self._session.execute(statement)
