"""Membership operations for the collaborators & sharing service (spec 33).

Listing, role changes, removal/leaving and ownership transfer. These functions
are transaction-bounded and raise typed domain errors. They are re-exported from
:mod:`inkstave.services.sharing`.

Access policy mirrors the project service (ADR 0007): a non-member sees ``404``;
a member who is not the owner gets ``403`` on owner-only operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.db.models.membership import (
    MembershipRole,
    MembershipStatus,
    ProjectMembership,
)
from inkstave.db.models.user import User
from inkstave.services.sharing_common import (
    MemberInfo,
    _active_project,
    membership_of,
    require_member,
    require_owner,
)
from inkstave.services.sharing_errors import (
    CannotChangeOwnerRoleError,
    InvalidRoleError,
    MemberNotFoundError,
    NotAMemberError,
    OwnerCannotLeaveError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def list_members(session: AsyncSession, project_id: UUID, actor_id: UUID) -> list[MemberInfo]:
    await require_member(session, project_id, actor_id)
    rows = (
        await session.execute(
            select(ProjectMembership, User)
            .join(User, User.id == ProjectMembership.user_id)
            .where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.status == MembershipStatus.active,
            )
            .order_by(ProjectMembership.created_at)
        )
    ).all()
    return [
        MemberInfo(
            user_id=m.user_id,
            name=u.display_name,
            email=u.email,
            role=m.role,
            status=m.status,
        )
        for m, u in rows
    ]


async def change_role(
    session: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
    target_user_id: UUID,
    new_role: str,
) -> MemberInfo:
    await require_owner(session, project_id, actor_id)  # 403 for non-owners first
    if new_role not in (MembershipRole.editor, MembershipRole.viewer):
        raise InvalidRoleError()  # 400 — 'owner' only via the transfer endpoint
    target = await membership_of(session, project_id, target_user_id)
    if target is None or target.status != MembershipStatus.active:
        raise MemberNotFoundError()
    if target.role == MembershipRole.owner:
        raise CannotChangeOwnerRoleError()
    target.role = new_role
    await session.flush()
    user = (await session.execute(select(User).where(User.id == target_user_id))).scalar_one()
    return MemberInfo(
        user_id=target.user_id,
        name=user.display_name,
        email=user.email,
        role=target.role,
        status=target.status,
    )


async def remove_member(
    session: AsyncSession, project_id: UUID, actor_id: UUID, target_user_id: UUID
) -> None:
    if target_user_id == actor_id:
        # Leave (self-remove).
        membership = await require_member(session, project_id, actor_id)
        if membership.role == MembershipRole.owner:
            raise OwnerCannotLeaveError()
        membership.status = MembershipStatus.left
        await session.flush()
        return

    await require_owner(session, project_id, actor_id)
    target = await membership_of(session, project_id, target_user_id)
    if target is None or target.status != MembershipStatus.active:
        raise MemberNotFoundError()
    if target.role == MembershipRole.owner:  # defensive; only the actor can be owner here
        raise OwnerCannotLeaveError()
    target.status = MembershipStatus.left
    await session.flush()


async def transfer_ownership(
    session: AsyncSession, project_id: UUID, actor_id: UUID, to_user_id: UUID
) -> MemberInfo:
    owner = await require_owner(session, project_id, actor_id)
    if to_user_id == actor_id:
        raise NotAMemberError()
    target = await membership_of(session, project_id, to_user_id)
    if target is None or target.status != MembershipStatus.active:
        raise NotAMemberError()

    # Demote the previous owner to editor first, then promote the target — two
    # flushes keep the "one owner" partial unique index satisfied at all times.
    owner.role = MembershipRole.editor
    await session.flush()
    target.role = MembershipRole.owner
    await session.flush()

    project = await _active_project(session, project_id)
    project.owner_id = to_user_id
    await session.flush()

    user = (await session.execute(select(User).where(User.id == to_user_id))).scalar_one()
    return MemberInfo(
        user_id=target.user_id,
        name=user.display_name,
        email=user.email,
        role=target.role,
        status=target.status,
    )
