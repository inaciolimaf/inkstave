"""Project service: ownership-scoped CRUD with soft delete (spec 11).

Ownership equals existence: a project the caller does not own is reported as
missing (``ProjectNotFoundError`` → 404), never 403, so existence is not leaked.
The session is committed by the ``get_db_session`` dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.project import Project
from inkstave.errors import NotFoundError
from inkstave.services.tree_service import ensure_root

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ProjectNotFoundError(NotFoundError):
    """Raised when a project is missing, soft-deleted, or owned by someone else."""

    error_type = "project_not_found"

    def __init__(self) -> None:
        super().__init__("Project not found.")


async def create_project(session: AsyncSession, owner_id: UUID, name: str) -> Project:
    project = Project(owner_id=owner_id, name=name)
    session.add(project)
    await session.flush()
    # Every project gets a file-tree root folder in the same transaction (spec 12).
    await ensure_root(session, project.id)
    # The creator is the owner member — the source of truth for sharing (spec 33).
    session.add(
        ProjectMembership(
            project_id=project.id,
            user_id=owner_id,
            role=MembershipRole.owner,
            status=MembershipStatus.active,
        )
    )
    await session.flush()
    await session.refresh(project)
    return project


async def get_owned_project(session: AsyncSession, owner_id: UUID, project_id: UUID) -> Project:
    stmt = select(Project).where(
        Project.id == project_id,
        Project.owner_id == owner_id,
        Project.deleted_at.is_(None),
    )
    project = (await session.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise ProjectNotFoundError()
    return project


async def list_projects(
    session: AsyncSession, owner_id: UUID, limit: int, offset: int
) -> tuple[list[Project], int]:
    base = (Project.owner_id == owner_id, Project.deleted_at.is_(None))

    total = (
        await session.execute(select(func.count()).select_from(Project).where(*base))
    ).scalar_one()

    rows = (
        await session.execute(
            select(Project)
            .where(*base)
            .order_by(Project.updated_at.desc(), Project.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows), int(total)


async def rename_project(
    session: AsyncSession, owner_id: UUID, project_id: UUID, name: str
) -> Project:
    project = await get_owned_project(session, owner_id, project_id)
    project.name = name
    # clock_timestamp() (wall clock) is strictly monotonic even within a single
    # transaction, so updated_at always advances on rename.
    project.updated_at = func.clock_timestamp()  # type: ignore[assignment]
    await session.flush()
    await session.refresh(project)
    return project


async def soft_delete_project(session: AsyncSession, owner_id: UUID, project_id: UUID) -> None:
    project = await get_owned_project(session, owner_id, project_id)
    project.deleted_at = func.now()  # type: ignore[assignment]
    await session.flush()
