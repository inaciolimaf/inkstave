"""Who may reach an agent session, shared by the agent's route modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status

from inkstave.core.db.ownership import get_owned
from inkstave.core.errors import AppError, NotFoundError
from inkstave.modules.agent.graph import repository as agent_repo
from inkstave.modules.agent.models import AgentSession
from inkstave.modules.projects import ProjectNotFoundError, role_for

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class NotProjectMemberError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_type = "not_project_member"

    def __init__(self) -> None:
        super().__init__("You are not a member of this project.")


async def require_member(session: AsyncSession, project_id: UUID, user_id: UUID) -> None:
    """404 for an unknown/deleted project, 403 for a non-member (spec 44)."""
    if not await agent_repo.project_is_live(session, project_id):
        raise ProjectNotFoundError()
    if await role_for(session, user_id, project_id) is None:
        raise NotProjectMemberError()


class RunNotFoundError(NotFoundError):
    error_type = "run_not_found"

    def __init__(self) -> None:
        super().__init__("This run does not exist in this session.")


async def owned_session(
    session: AsyncSession, project_id: UUID, session_id: UUID, user_id: UUID
) -> AgentSession:
    return await get_owned(
        session, AgentSession, session_id, user_id, not_found=ProjectNotFoundError(), project_id=project_id
    )


async def owned_run(
    session: AsyncSession, project_id: UUID, session_id: UUID, run_id: UUID, user_id: UUID
) -> AgentSession:
    """The session, when ``run_id`` is one of its runs: the active one, or one with audit rows in it."""
    row = await owned_session(session, project_id, session_id, user_id)
    if row.active_run_id == run_id:
        return row
    if not await agent_repo.run_belongs_to_session(session, session_id, run_id):
        raise RunNotFoundError()
    return row
