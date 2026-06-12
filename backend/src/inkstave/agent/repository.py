"""Async CRUD for agent sessions + messages (spec 41)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select

from inkstave.agent.models import AgentMessage, AgentSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create_session(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    model: str,
    title: str | None = None,
) -> AgentSession:
    session = AgentSession(
        project_id=project_id, user_id=user_id, model=model, title=title
    )
    db.add(session)
    await db.flush()
    return session


async def get_session(db: AsyncSession, session_id: UUID) -> AgentSession | None:
    return await db.get(AgentSession, session_id)


async def list_sessions(
    db: AsyncSession, *, project_id: UUID, user_id: UUID
) -> list[AgentSession]:
    rows = await db.execute(
        select(AgentSession)
        .where(AgentSession.project_id == project_id, AgentSession.user_id == user_id)
        .order_by(AgentSession.updated_at.desc())
    )
    return list(rows.scalars())


async def list_messages(db: AsyncSession, session_id: UUID) -> list[AgentMessage]:
    rows = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.seq)
    )
    return list(rows.scalars())


async def next_seq(db: AsyncSession, session_id: UUID) -> int:
    value = await db.scalar(
        select(func.max(AgentMessage.seq)).where(AgentMessage.session_id == session_id)
    )
    return 0 if value is None else int(value) + 1


async def add_message(
    db: AsyncSession,
    *,
    session_id: UUID,
    seq: int,
    role: str,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
    token_usage: dict[str, Any] | None = None,
) -> AgentMessage:
    message = AgentMessage(
        session_id=session_id,
        seq=seq,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        token_usage=token_usage,
    )
    db.add(message)
    await db.flush()
    return message
