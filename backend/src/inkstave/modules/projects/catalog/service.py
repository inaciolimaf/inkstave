"""Project service: ownership-scoped CRUD with soft delete (spec 11).

Ownership equals existence: a project the caller does not own is reported as
missing (``ProjectNotFoundError`` → 404), never 403, so existence is not leaked.
The session is committed by the ``get_db_session`` dependency.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from inkstave.core.errors import NotFoundError
from inkstave.modules.auth import User
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.modules.projects.models.project import Project
from inkstave.modules.projects.tree.service import ensure_root

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncSession


class ProjectNotFoundError(NotFoundError):
    """Raised when a project is missing, soft-deleted, or owned by someone else."""

    error_type = "project_not_found"

    def __init__(self) -> None:
        super().__init__("Project not found.")


async def create_project(
    session: AsyncSession, owner_id: UUID, name: str, spellcheck_language: str = "en-US"
) -> Project:
    project = Project(owner_id=owner_id, name=name, spellcheck_language=spellcheck_language)
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


async def get_project_name(session: AsyncSession, project_id: UUID) -> str | None:
    name: str | None = await session.scalar(select(Project.name).where(Project.id == project_id))
    return name


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


class ProjectScope(enum.StrEnum):
    """Which memberships a listing covers: all of them, the caller's own, or the ones shared with them."""

    all = "all"
    owned = "owned"
    shared = "shared"


@dataclass(frozen=True)
class ListedProject:
    """One row of a listing: the project, the caller's role in it and the owner's display name."""

    project: Project
    role: MembershipRole
    owner_name: str


_SHARED_ROLES = (MembershipRole.editor, MembershipRole.viewer)


def _listing_conditions(user_id: UUID, scope: ProjectScope) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        ProjectMembership.user_id == user_id,
        ProjectMembership.status == MembershipStatus.active,
        Project.deleted_at.is_(None),
    ]
    if scope is ProjectScope.owned:
        conditions.append(ProjectMembership.role == MembershipRole.owner)
    elif scope is ProjectScope.shared:
        conditions.append(ProjectMembership.role.in_(_SHARED_ROLES))
    return conditions


async def _count_listing(session: AsyncSession, conditions: list[ColumnElement[bool]]) -> int:
    stmt = (
        select(func.count())
        .select_from(Project)
        .join(ProjectMembership, ProjectMembership.project_id == Project.id)
        .where(*conditions)
    )
    return int((await session.execute(stmt)).scalar_one())


async def list_projects(
    session: AsyncSession, user_id: UUID, scope: ProjectScope, limit: int, offset: int
) -> tuple[list[ListedProject], int]:
    """Live projects where ``user_id`` is an active member, in one query per page.

    The total is a window count on the same statement. A page past the end has no
    row to carry it, so only that case runs a second count.
    """
    conditions = _listing_conditions(user_id, scope)
    stmt = (
        select(Project, ProjectMembership.role, User.display_name, func.count().over().label("total"))
        .join(ProjectMembership, ProjectMembership.project_id == Project.id)
        .join(User, User.id == Project.owner_id)
        .where(*conditions)
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    listed = [
        ListedProject(project=p, role=MembershipRole(role), owner_name=name) for p, role, name, _ in rows
    ]
    if rows:
        return listed, int(rows[0].total)
    if offset == 0:
        return listed, 0
    return listed, await _count_listing(session, conditions)


async def rename_project(session: AsyncSession, owner_id: UUID, project_id: UUID, name: str) -> Project:
    project = await get_owned_project(session, owner_id, project_id)
    project.name = name
    # clock_timestamp() (wall clock) is strictly monotonic even within a single
    # transaction, so updated_at always advances on rename.
    project.updated_at = func.clock_timestamp()
    await session.flush()
    await session.refresh(project)
    return project


async def soft_delete_project(session: AsyncSession, owner_id: UUID, project_id: UUID) -> None:
    project = await get_owned_project(session, owner_id, project_id)
    project.deleted_at = func.now()
    await session.flush()


async def set_spellcheck_language(session: AsyncSession, project: Project, language: str) -> Project:
    """Set the project's spell-check language (spec 113). The caller has checked the capability."""
    project.spellcheck_language = language
    await session.flush()
    await session.refresh(project)
    return project
