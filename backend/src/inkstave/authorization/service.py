"""The authorization service (spec 34).

Resolves a user's effective role on a project from spec-33 memberships and
authorizes capabilities against the matrix. Error semantics (ADR 0034):
non-member of a project → 404 (existence not leaked); member with an insufficient
role → 403 ``insufficient_role``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.authorization.capabilities import Capability, capabilities_for
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.project import Project
from inkstave.errors import ForbiddenError, NotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class InsufficientRoleError(ForbiddenError):
    error_type = "insufficient_role"

    def __init__(self) -> None:
        super().__init__("Your role does not permit this action.")


async def role_for(session: AsyncSession, user_id: UUID, project_id: UUID) -> MembershipRole | None:
    """The user's effective role on a *live* project, or ``None`` (non-member).

    A soft-deleted or missing project also yields ``None`` so callers report 404.
    """
    project_exists = (
        await session.execute(
            select(Project.id).where(Project.id == project_id, Project.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if project_exists is None:
        return None
    role = (
        await session.execute(
            select(ProjectMembership.role).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
                ProjectMembership.status == MembershipStatus.active,
            )
        )
    ).scalar_one_or_none()
    return MembershipRole(role) if role is not None else None


class ProjectAccessNotFoundError(NotFoundError):
    """A project is missing, soft-deleted, or the user is not a member.

    Existence is not leaked: a non-member sees the same 404 as for an absent
    project (ADR 0034).
    """

    error_type = "not_found"

    def __init__(self) -> None:
        super().__init__("Project not found.")


class AuthorizationService:
    """Spec-34 §5.2 authorization facade.

    Deliberate, reviewed design note (issue #136): the production project-scoped
    gate is the ``require_capability`` FastAPI dependency in
    ``authorization/dependencies.py``, which owns the **request-scoped membership
    cache** (one lookup per project per request) and is integration-tested for its
    404/403 error semantics. This class is a thin facade over the same building
    blocks (``role_for`` + ``capabilities_for``) so callers and tests can use the
    §5.2 method shape (``get_role``/``get_capabilities``/``authorize``/``can``)
    without depending on FastAPI. It intentionally does **not** re-implement or
    move the request-scoped cache (that stays in ``dependencies.py``, out of this
    fix-pack's scope).

    Known test gap (spec 34 §8): the "request-scoped caching does a single
    membership lookup" query-count assertion belongs to an integration test file
    outside this fix-pack's scope and is therefore **deferred** — it is not added
    here. The caching behaviour itself lives in ``dependencies.py::_resolve``.
    """

    def __init__(self, session: AsyncSession, *, compile_for_viewers: bool = True) -> None:
        self._session = session
        self._compile_for_viewers = compile_for_viewers

    async def get_role(self, user_id: UUID, project_id: UUID) -> MembershipRole | None:
        """The user's effective role on the project, or ``None`` (non-member/absent)."""
        return await role_for(self._session, user_id, project_id)

    async def get_capabilities(self, user_id: UUID, project_id: UUID) -> frozenset[Capability]:
        """The capability set the user holds on the project (empty for non-members)."""
        role = await self.get_role(user_id, project_id)
        return capabilities_for(role, compile_for_viewers=self._compile_for_viewers)

    async def authorize(self, user_id: UUID, project_id: UUID, cap: Capability) -> MembershipRole:
        """Authorize ``cap`` for the user, mirroring the production gate's semantics.

        Raises ``ProjectAccessNotFoundError`` (404) for a missing project or a
        non-member (existence not leaked), and ``InsufficientRoleError`` (403)
        for a member whose role lacks ``cap``. Returns the effective role on
        success.
        """
        role = await self.get_role(user_id, project_id)
        if role is None:
            raise ProjectAccessNotFoundError()
        if cap not in capabilities_for(role, compile_for_viewers=self._compile_for_viewers):
            raise InsufficientRoleError()
        return role

    async def can(self, user_id: UUID, project_id: UUID, cap: Capability) -> bool:
        """Whether the user holds ``cap`` on the project (never raises)."""
        return cap in await self.get_capabilities(user_id, project_id)
