"""Invite operations for the collaborators & sharing service (spec 33).

Creating, listing, revoking, previewing, accepting and declining invites. These
functions are transaction-bounded and raise typed domain errors. They are
re-exported from :mod:`inkstave.services.sharing`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from inkstave.db.models.invite import InviteStatus, ProjectInvite
from inkstave.db.models.membership import (
    MembershipRole,
    MembershipStatus,
    ProjectMembership,
)
from inkstave.db.models.project import Project
from inkstave.db.models.user import User
from inkstave.services.sharing_common import (
    _now,
    generate_token,
    hash_token,
    membership_of,
    require_owner,
)
from inkstave.services.sharing_errors import (
    AlreadyMemberError,
    InviteEmailMismatchError,
    InviteGoneError,
    InviteNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _reject_if_member(session: AsyncSession, project_id: UUID, email: str) -> None:
    """409 if the email already belongs to an active member of the project."""
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()
    if user is None:
        return
    member = await membership_of(session, project_id, user.id)
    if member is not None and member.status == MembershipStatus.active:
        raise AlreadyMemberError()


async def _pending_invite(
    session: AsyncSession, project_id: UUID, email: str
) -> ProjectInvite | None:
    return (
        await session.execute(
            select(ProjectInvite).where(
                ProjectInvite.project_id == project_id,
                func.lower(ProjectInvite.email) == email,
                ProjectInvite.status == InviteStatus.pending,
            )
        )
    ).scalar_one_or_none()


async def create_invite(
    session: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
    email: str,
    role: str,
    *,
    ttl_days: int,
) -> tuple[ProjectInvite, str]:
    await require_owner(session, project_id, actor_id)
    normalized = email.strip().lower()
    await _reject_if_member(session, project_id, normalized)

    raw_token = generate_token()
    token_hash = hash_token(raw_token)
    expires_at = _now() + timedelta(days=ttl_days)

    # Refresh an existing pending invite for the same (project, email) instead of
    # creating a duplicate.
    invite = await _pending_invite(session, project_id, normalized)
    if invite is None:
        invite = ProjectInvite(
            project_id=project_id,
            email=normalized,
            status=InviteStatus.pending,
        )
        session.add(invite)
    invite.role = role
    invite.token_hash = token_hash
    invite.expires_at = expires_at
    invite.invited_by = actor_id
    await session.flush()
    return invite, raw_token


async def list_invites(
    session: AsyncSession, project_id: UUID, actor_id: UUID
) -> list[ProjectInvite]:
    await require_owner(session, project_id, actor_id)
    rows = (
        await session.execute(
            select(ProjectInvite)
            .where(
                ProjectInvite.project_id == project_id,
                ProjectInvite.status == InviteStatus.pending,
            )
            .order_by(ProjectInvite.created_at.desc())
        )
    ).scalars()
    return list(rows)


async def revoke_invite(
    session: AsyncSession, project_id: UUID, actor_id: UUID, invite_id: UUID
) -> None:
    await require_owner(session, project_id, actor_id)
    invite = (
        await session.execute(
            select(ProjectInvite).where(
                ProjectInvite.id == invite_id,
                ProjectInvite.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if invite is None:
        raise InviteNotFoundError()
    if invite.status == InviteStatus.pending:
        invite.status = InviteStatus.revoked
        invite.responded_at = _now()
        await session.flush()


async def _invite_by_token(session: AsyncSession, raw_token: str) -> ProjectInvite:
    invite = (
        await session.execute(
            select(ProjectInvite).where(ProjectInvite.token_hash == hash_token(raw_token))
        )
    ).scalar_one_or_none()
    if invite is None:
        raise InviteNotFoundError()
    return invite


async def get_invite_preview(
    session: AsyncSession, raw_token: str
) -> tuple[ProjectInvite, Project, User]:
    invite = await _invite_by_token(session, raw_token)
    if invite.status != InviteStatus.pending or invite.expires_at < _now():
        raise InviteGoneError()
    project = (
        await session.execute(
            select(Project).where(Project.id == invite.project_id, Project.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if project is None:
        raise InviteGoneError()
    inviter = (await session.execute(select(User).where(User.id == invite.invited_by))).scalar_one()
    return invite, project, inviter


async def _already_accepted(
    session: AsyncSession, invite: ProjectInvite, actor: User
) -> tuple[UUID, str]:
    """Idempotent re-accept: succeeds only while the membership is still active."""
    member = await membership_of(session, invite.project_id, actor.id)
    if member is not None and member.status == MembershipStatus.active:
        return invite.project_id, member.role
    raise InviteGoneError()


async def _require_pending(session: AsyncSession, invite: ProjectInvite) -> None:
    """Raise unless the invite is still pending and unexpired, expiring it if due."""
    if invite.status == InviteStatus.pending and invite.expires_at >= _now():
        return
    if invite.status == InviteStatus.pending:
        invite.status = InviteStatus.expired
        await session.flush()
    raise InviteGoneError()


async def _grant_membership(
    session: AsyncSession, invite: ProjectInvite, actor: User
) -> ProjectMembership:
    """Create or re-activate the actor's membership; an owner keeps their role."""
    member = await membership_of(session, invite.project_id, actor.id)
    if member is None:
        member = ProjectMembership(
            project_id=invite.project_id,
            user_id=actor.id,
            role=invite.role,
            status=MembershipStatus.active,
        )
        session.add(member)
    elif member.role != MembershipRole.owner:
        member.role = invite.role
        member.status = MembershipStatus.active
    return member


async def accept_invite(session: AsyncSession, raw_token: str, actor: User) -> tuple[UUID, str]:
    invite = await _invite_by_token(session, raw_token)
    if invite.status == InviteStatus.accepted:
        return await _already_accepted(session, invite, actor)

    await _require_pending(session, invite)
    if actor.email.strip().lower() != invite.email.strip().lower():
        raise InviteEmailMismatchError()

    member = await _grant_membership(session, invite, actor)
    invite.status = InviteStatus.accepted
    invite.responded_at = _now()
    await session.flush()
    return invite.project_id, member.role


async def decline_invite(session: AsyncSession, raw_token: str) -> None:
    invite = await _invite_by_token(session, raw_token)
    if invite.status != InviteStatus.pending or invite.expires_at < _now():
        if invite.status == InviteStatus.pending:
            invite.status = InviteStatus.expired
            await session.flush()
        raise InviteGoneError()
    invite.status = InviteStatus.declined
    invite.responded_at = _now()
    await session.flush()
