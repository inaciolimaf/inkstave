"""FastAPI authorization dependencies (spec 34).

`require_capability(cap)` is the single project-scoped gate retrofitted onto every
project route: it resolves the current user, binds ``project_id`` from the path,
authorizes the capability against the role→capability matrix, and returns the
loaded :class:`Project` for the handler (matching the old ``owned_project`` shape).

The project row *and* the caller's role are fetched in **one** outer-join query
(cached per request) so the guard adds no extra round trips over the old
owner-only check.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import and_, select

from inkstave.auth.dependencies import get_current_user
from inkstave.authorization.capabilities import Capability, capabilities_for
from inkstave.authorization.service import InsufficientRoleError
from inkstave.config import Settings
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.project import Project
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_settings_dep
from inkstave.services.project import ProjectNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.db.models.user import User


async def _resolve(
    request: Request, session: AsyncSession, user_id: UUID, project_id: UUID
) -> tuple[Project | None, MembershipRole | None]:
    """Load (live project, caller's active role) in one query, cached per request."""
    cache: dict[UUID, tuple[Project | None, MembershipRole | None]] = (
        getattr(request.state, "authz_cache", None) or {}
    )
    request.state.authz_cache = cache
    if project_id not in cache:
        row = (
            await session.execute(
                select(Project, ProjectMembership.role)
                .outerjoin(
                    ProjectMembership,
                    and_(
                        ProjectMembership.project_id == Project.id,
                        ProjectMembership.user_id == user_id,
                        ProjectMembership.status == MembershipStatus.active,
                    ),
                )
                .where(Project.id == project_id, Project.deleted_at.is_(None))
            )
        ).first()
        if row is None:
            cache[project_id] = (None, None)
        else:
            project, role = row
            cache[project_id] = (project, MembershipRole(role) if role is not None else None)
    return cache[project_id]


def require_capability(cap: Capability) -> Callable[..., Awaitable[Project]]:
    """Build a dependency that authorizes ``cap`` and returns the project."""

    async def dependency(
        project_id: UUID,  # bound + validated from the {project_id} path segment
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
        settings: Settings = Depends(get_settings_dep),
    ) -> Project:
        project, role = await _resolve(request, session, user.id, project_id)
        if project is None or role is None:
            raise ProjectNotFoundError()  # 404 — missing project or non-member
        if cap not in capabilities_for(
            role, compile_for_viewers=settings.compile_allowed_for_viewers
        ):
            raise InsufficientRoleError()  # 403
        return project

    # Marker so the guard-coverage audit (spec 35) can detect this guard on a route.
    dependency.__authz_capability__ = cap  # type: ignore[attr-defined]
    return dependency
