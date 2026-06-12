"""Shared value objects, token helpers and access guards for sharing (spec 33).

These pieces are used by both the membership and invite operations. They are
re-exported from :mod:`inkstave.services.sharing`.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.db.models.membership import (
    MembershipRole,
    MembershipStatus,
    ProjectMembership,
)
from inkstave.db.models.project import Project
from inkstave.services.project import ProjectNotFoundError
from inkstave.services.sharing_errors import NotProjectOwnerError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_TOKEN_BYTES = 32


# --- value objects --------------------------------------------------------- #


@dataclass(frozen=True)
class MemberInfo:
    user_id: UUID
    name: str
    email: str
    role: str
    status: str


# --- helpers --------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(UTC)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


async def _active_project(session: AsyncSession, project_id: UUID) -> Project:
    project = (
        await session.execute(
            select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if project is None:
        raise ProjectNotFoundError()
    return project


async def membership_of(
    session: AsyncSession, project_id: UUID, user_id: UUID
) -> ProjectMembership | None:
    return (
        await session.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def require_member(
    session: AsyncSession, project_id: UUID, user_id: UUID
) -> ProjectMembership:
    """Active member of a live project, else 404 (existence not leaked)."""
    await _active_project(session, project_id)
    membership = await membership_of(session, project_id, user_id)
    if membership is None or membership.status != MembershipStatus.active:
        raise ProjectNotFoundError()
    return membership


async def require_owner(
    session: AsyncSession, project_id: UUID, user_id: UUID
) -> ProjectMembership:
    """Owner of a live project: 404 for non-members, 403 for non-owner members."""
    membership = await require_member(session, project_id, user_id)
    if membership.role != MembershipRole.owner:
        raise NotProjectOwnerError()
    return membership
