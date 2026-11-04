"""Shared value objects, token helpers and access guards for sharing (spec 33).

These pieces are used by both the membership and invite operations. They are
re-exported from :mod:`inkstave.modules.projects.sharing`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.modules.projects.catalog.service import ProjectNotFoundError
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.modules.projects.models.project import Project
from inkstave.modules.projects.sharing.errors import NotProjectOwnerError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class MemberInfo:
    user_id: UUID
    name: str
    email: str
    role: str
    status: str
    via_link: bool = False


def _now() -> datetime:
    return datetime.now(UTC)


def detach_from_link(membership: ProjectMembership) -> None:
    """Forget any share-link attribution: the access no longer depends on a link (spec 116)."""
    membership.via_link_id = None
    membership.role_before_link = None


async def _active_project(session: AsyncSession, project_id: UUID) -> Project:
    project = (
        await session.execute(select(Project).where(Project.id == project_id, Project.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if project is None:
        raise ProjectNotFoundError()
    return project


async def membership_of(session: AsyncSession, project_id: UUID, user_id: UUID) -> ProjectMembership | None:
    return (
        await session.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def require_member(session: AsyncSession, project_id: UUID, user_id: UUID) -> ProjectMembership:
    """Active member of a live project, else 404 (existence not leaked)."""
    await _active_project(session, project_id)
    membership = await membership_of(session, project_id, user_id)
    if membership is None or membership.status != MembershipStatus.active:
        raise ProjectNotFoundError()
    return membership


async def require_owner(session: AsyncSession, project_id: UUID, user_id: UUID) -> ProjectMembership:
    """Owner of a live project: 404 for non-members, 403 for non-owner members."""
    membership = await require_member(session, project_id, user_id)
    if membership.role != MembershipRole.owner:
        raise NotProjectOwnerError()
    return membership
