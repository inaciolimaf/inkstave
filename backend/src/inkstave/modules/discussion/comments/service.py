"""Comment threads: anchors, messages, mentions, replies and resolve (spec 118).

The service never commits: the request's unit of work does. Mentions are checked against the active
members here, so a stranger's id in the request is dropped. Replies notify the earlier participants in
the bell only. The routes publish the returned event after the commit (see ``publish.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth import User
from inkstave.modules.discussion.comments.anchors import decode_anchor, encode_anchor
from inkstave.modules.discussion.comments.errors import (
    CommentMessageNotFoundError,
    CommentThreadNotFoundError,
    NotATextDocumentError,
)
from inkstave.modules.discussion.comments.models import CommentMessage, CommentThread
from inkstave.modules.discussion.comments.outcome import CommentOutcome, MentionMail, excerpt
from inkstave.modules.discussion.comments.schemas import (
    CommentMessageRead,
    CommentMessageWrite,
    CommentThreadCreate,
    CommentThreadRead,
)
from inkstave.modules.discussion.errors import NotMessageAuthorError
from inkstave.modules.discussion.schemas import ChatAuthor
from inkstave.modules.notifications import NotificationType, notify_comment_users
from inkstave.modules.projects import TreeEntityType, active_member_ids, get_entity

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.modules.projects import Project

ThreadStatus = Literal["open", "resolved", "all"]


def _author(users: dict[UUID, User], user_id: UUID | None) -> ChatAuthor | None:
    user = users.get(user_id) if user_id is not None else None
    return ChatAuthor(id=user.id, display_name=user.display_name) if user is not None else None


def _message_read(message: CommentMessage, users: dict[UUID, User]) -> CommentMessageRead:
    deleted = message.deleted_at is not None
    return CommentMessageRead(
        id=message.id,
        body=None if deleted else message.body,
        author=_author(users, message.author_id),
        mentions=list(message.mentions),
        created_at=message.created_at,
        edited_at=message.edited_at,
        deleted=deleted,
    )


def _thread_read(
    thread: CommentThread, messages: list[CommentMessageRead], users: dict[UUID, User]
) -> CommentThreadRead:
    return CommentThreadRead(
        id=thread.id,
        document_id=thread.document_id,
        anchor_start=encode_anchor(thread.anchor_start),
        anchor_end=encode_anchor(thread.anchor_end),
        quoted_text=thread.quoted_text,
        author=_author(users, thread.created_by),
        created_at=thread.created_at,
        resolved_at=thread.resolved_at,
        resolved_by=_author(users, thread.resolved_by),
        messages=messages,
    )


def _notification_payload(project: Project, author: User, thread: CommentThread, body: str) -> dict[str, str]:
    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "thread_id": str(thread.id),
        "document_id": str(thread.document_id),
        "author_name": author.display_name,
        "excerpt": excerpt(body),
    }


def _comment_url(project_id: UUID, thread_id: UUID) -> str:
    base = get_settings().frontend_url.rstrip("/")
    return f"{base}/projects/{project_id}?thread={thread_id}"


class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_threads(
        self, project_id: UUID, *, document_id: UUID | None, status: ThreadStatus
    ) -> list[CommentThreadRead]:
        statement = select(CommentThread).where(CommentThread.project_id == project_id)
        if document_id is not None:
            statement = statement.where(CommentThread.document_id == document_id)
        if status == "open":
            statement = statement.where(CommentThread.resolved_at.is_(None))
        elif status == "resolved":
            statement = statement.where(CommentThread.resolved_at.is_not(None))
        statement = statement.order_by(CommentThread.created_at, CommentThread.id)
        threads = list((await self._session.execute(statement)).scalars())
        return await self._reads(threads)

    async def create_thread(
        self, project: Project, author: User, payload: CommentThreadCreate
    ) -> CommentOutcome[CommentThreadRead]:
        await get_entity(
            self._session,
            project.id,
            payload.document_id,
            expected_type=TreeEntityType.doc,
            wrong_type_error=NotATextDocumentError,
        )
        now = datetime.now(UTC)
        thread = CommentThread(
            project_id=project.id,
            document_id=payload.document_id,
            anchor_start=decode_anchor(payload.anchor_start),
            anchor_end=decode_anchor(payload.anchor_end),
            quoted_text=payload.quoted_text,
            created_by=author.id,
            created_at=now,
        )
        self._session.add(thread)
        await self._session.flush()
        mentioned = await self._valid_mentions(project.id, author.id, payload.mentions)
        await self._add_message(thread.id, author.id, payload.body, mentioned, now)
        read = (await self._reads([thread]))[0]
        mails = await self._notify_mentions(project, author, thread, payload.body, mentioned)
        return CommentOutcome(read, ("comment.thread_created", read.model_dump(mode="json")), mails)

    async def add_reply(
        self, project: Project, author: User, thread_id: UUID, payload: CommentMessageWrite
    ) -> CommentOutcome[CommentMessageRead]:
        thread = await self._thread(project.id, thread_id)
        mentioned = await self._valid_mentions(project.id, author.id, payload.mentions)
        message = await self._add_message(thread.id, author.id, payload.body, mentioned, datetime.now(UTC))
        read = _message_read(message, {author.id: author})
        recipients = await self._reply_recipients(project.id, thread, author.id, exclude=mentioned)
        if recipients:
            await notify_comment_users(
                self._session,
                notification_type=NotificationType.comment_reply,
                user_ids=recipients,
                payload=_notification_payload(project, author, thread, payload.body),
            )
        mails = await self._notify_mentions(project, author, thread, payload.body, mentioned)
        event = ("comment.message_created", {"thread_id": str(thread.id), "message": _dump(read)})
        return CommentOutcome(read, event, mails)

    async def edit_message(
        self,
        project: Project,
        author: User,
        thread_id: UUID,
        message_id: UUID,
        payload: CommentMessageWrite,
    ) -> CommentOutcome[CommentMessageRead]:
        thread = await self._thread(project.id, thread_id)
        message = await self._live_message(thread.id, message_id)
        if message.author_id != author.id:
            raise NotMessageAuthorError()
        previous = set(message.mentions)
        mentioned = await self._valid_mentions(project.id, author.id, payload.mentions)
        message.body = payload.body
        message.mentions = mentioned
        message.edited_at = datetime.now(UTC)
        await self._session.flush()
        # Only people newly mentioned are notified: an edit does not repeat the earlier mentions.
        added = [user_id for user_id in mentioned if user_id not in previous]
        mails = await self._notify_mentions(project, author, thread, payload.body, added)
        read = _message_read(message, {author.id: author})
        event = ("comment.message_updated", {"thread_id": str(thread.id), "message": _dump(read)})
        return CommentOutcome(read, event, mails)

    async def delete_message(
        self, project_id: UUID, author_id: UUID, thread_id: UUID, message_id: UUID
    ) -> CommentOutcome[None]:
        """Soft-delete an own message; the last live message of a thread takes the whole thread with it."""
        thread = await self._thread(project_id, thread_id)
        message = await self._message(thread.id, message_id)
        if message.author_id != author_id:
            raise NotMessageAuthorError()
        if message.deleted_at is not None:
            return CommentOutcome(None)  # already deleted: a no-op, as on the chat
        thread_deleted = not await self._has_other_live_messages(thread.id, message.id)
        if thread_deleted:
            await self._session.delete(thread)  # the database cascades to the messages
        else:
            message.deleted_at = datetime.now(UTC)
        await self._session.flush()
        event = (
            "comment.message_deleted",
            {"thread_id": str(thread_id), "message_id": str(message_id), "thread_deleted": thread_deleted},
        )
        return CommentOutcome(None, event)

    async def set_resolved(
        self, project_id: UUID, actor: User, thread_id: UUID, *, resolved: bool
    ) -> CommentOutcome[CommentThreadRead]:
        thread = await self._thread(project_id, thread_id)
        changed = (thread.resolved_at is None) == resolved
        if changed:
            thread.resolved_at = datetime.now(UTC) if resolved else None
            thread.resolved_by = actor.id if resolved else None
            await self._session.flush()
        read = (await self._reads([thread]))[0]
        event_type = "comment.thread_resolved" if resolved else "comment.thread_reopened"
        event = (event_type, _dump(read)) if changed else None
        return CommentOutcome(read, event)

    async def _thread(self, project_id: UUID, thread_id: UUID) -> CommentThread:
        thread = await self._session.get(CommentThread, thread_id)
        if thread is None or thread.project_id != project_id:
            raise CommentThreadNotFoundError()
        return thread

    async def _message(self, thread_id: UUID, message_id: UUID) -> CommentMessage:
        message = await self._session.get(CommentMessage, message_id)
        if message is None or message.thread_id != thread_id:
            raise CommentMessageNotFoundError()
        return message

    async def _live_message(self, thread_id: UUID, message_id: UUID) -> CommentMessage:
        message = await self._message(thread_id, message_id)
        if message.deleted_at is not None:
            raise CommentMessageNotFoundError()
        return message

    async def _has_other_live_messages(self, thread_id: UUID, message_id: UUID) -> bool:
        count = await self._session.scalar(
            select(func.count())
            .select_from(CommentMessage)
            .where(
                CommentMessage.thread_id == thread_id,
                CommentMessage.deleted_at.is_(None),
                CommentMessage.id != message_id,
            )
        )
        return bool(count)

    async def _add_message(
        self, thread_id: UUID, author_id: UUID, body: str, mentions: list[UUID], now: datetime
    ) -> CommentMessage:
        message = CommentMessage(
            thread_id=thread_id, author_id=author_id, body=body, mentions=mentions, created_at=now
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def _valid_mentions(self, project_id: UUID, author_id: UUID, requested: list[UUID]) -> list[UUID]:
        """Requested ids that are active members other than the author, each once, in request order."""
        candidates = [user_id for user_id in dict.fromkeys(requested) if user_id != author_id]
        active = await active_member_ids(self._session, project_id, candidates)
        return [user_id for user_id in candidates if user_id in active]

    async def _reply_recipients(
        self, project_id: UUID, thread: CommentThread, author_id: UUID, *, exclude: Iterable[UUID]
    ) -> list[UUID]:
        """Earlier participants still in the project: the creator and every message author."""
        authors = await self._session.execute(
            select(CommentMessage.author_id).where(CommentMessage.thread_id == thread.id).distinct()
        )
        candidates = {user_id for user_id in [thread.created_by, *authors.scalars()] if user_id is not None}
        candidates -= {author_id, *exclude}
        active = await active_member_ids(self._session, project_id, candidates)
        return sorted(active, key=str)

    async def _notify_mentions(
        self,
        project: Project,
        author: User,
        thread: CommentThread,
        body: str,
        mentioned: list[UUID],
    ) -> tuple[MentionMail, ...]:
        """The bell rows for the mentioned members, and the e-mails for those with an address."""
        if not mentioned:
            return ()
        await notify_comment_users(
            self._session,
            notification_type=NotificationType.comment_mention,
            user_ids=mentioned,
            payload=_notification_payload(project, author, thread, body),
        )
        users = await self._users(mentioned)
        context_base = {
            "project_name": project.name,
            "author_name": author.display_name,
            "excerpt": excerpt(body),
            "comment_url": _comment_url(project.id, thread.id),
        }
        return tuple(MentionMail(to=user.email, context=dict(context_base)) for user in users.values())

    async def _reads(self, threads: list[CommentThread]) -> list[CommentThreadRead]:
        if not threads:
            return []
        rows = await self._session.execute(
            select(CommentMessage)
            .where(CommentMessage.thread_id.in_([thread.id for thread in threads]))
            .order_by(CommentMessage.created_at, CommentMessage.id)
        )
        messages = list(rows.scalars())
        user_ids = {uid for thread in threads for uid in (thread.created_by, thread.resolved_by) if uid}
        user_ids |= {message.author_id for message in messages if message.author_id is not None}
        users = await self._users(user_ids)
        by_thread: dict[UUID, list[CommentMessageRead]] = {}
        for message in messages:
            by_thread.setdefault(message.thread_id, []).append(_message_read(message, users))
        return [_thread_read(thread, by_thread.get(thread.id, []), users) for thread in threads]

    async def _users(self, user_ids: Iterable[UUID]) -> dict[UUID, User]:
        wanted = list(set(user_ids))
        if not wanted:
            return {}
        rows = await self._session.execute(select(User).where(User.id.in_(wanted)))
        return {user.id: user for user in rows.scalars()}


def _dump(model: BaseModel) -> dict[str, Any]:
    """The JSON form of a read model, as it goes on the event stream."""
    return model.model_dump(mode="json")
