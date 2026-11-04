"""Owner operations on share links (spec 116): list, create or rotate, turn off.

A link grants one role to whoever opens it. Turning a link off, or rotating it, takes back exactly
what that link granted: see :func:`_take_back`. These functions are transaction-bounded and raise
typed domain errors, like the rest of the sharing service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.modules.auth import generate_token, hash_token
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.modules.projects.models.share_link import ProjectShareLink
from inkstave.modules.projects.sharing.common import _now, detach_from_link, require_owner
from inkstave.modules.projects.sharing.errors import ShareLinkNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _active_link_for_role(
    session: AsyncSession, project_id: UUID, role: str
) -> ProjectShareLink | None:
    return (
        await session.execute(
            select(ProjectShareLink).where(
                ProjectShareLink.project_id == project_id,
                ProjectShareLink.role == role,
                ProjectShareLink.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _take_back(session: AsyncSession, link: ProjectShareLink) -> None:
    """Revoke ``link`` and undo what it granted.

    A member the link upgraded returns to ``role_before_link``; a member the link created leaves the
    project (``left``). Members whose role the owner set by hand, or who accepted an e-mail invite, no
    longer carry the link and are not touched. The owner row is never changed.
    """
    link.revoked_at = _now()
    await session.flush()
    members = (
        await session.execute(select(ProjectMembership).where(ProjectMembership.via_link_id == link.id))
    ).scalars()
    for member in members:
        if member.role != MembershipRole.owner:
            if member.role_before_link is not None:
                member.role = member.role_before_link
            else:
                member.status = MembershipStatus.left
        detach_from_link(member)
    await session.flush()


async def list_share_links(session: AsyncSession, project_id: UUID, actor_id: UUID) -> list[ProjectShareLink]:
    """Active links of the project. Tokens are never stored, so none is returned."""
    await require_owner(session, project_id, actor_id)
    rows = await session.execute(
        select(ProjectShareLink)
        .where(ProjectShareLink.project_id == project_id, ProjectShareLink.revoked_at.is_(None))
        .order_by(ProjectShareLink.created_at)
    )
    return list(rows.scalars())


async def create_share_link(
    session: AsyncSession, project_id: UUID, actor_id: UUID, role: str
) -> tuple[ProjectShareLink, str]:
    """Turn a link on, or rotate it when one is active. Returns the link and its raw token, once."""
    await require_owner(session, project_id, actor_id)
    previous = await _active_link_for_role(session, project_id, role)
    if previous is not None:
        await _take_back(session, previous)

    raw_token = generate_token()
    link = ProjectShareLink(
        project_id=project_id,
        role=role,
        token_hash=hash_token(raw_token),
        created_by=actor_id,
    )
    session.add(link)
    await session.flush()
    return link, raw_token


async def revoke_share_link(session: AsyncSession, project_id: UUID, actor_id: UUID, link_id: UUID) -> None:
    await require_owner(session, project_id, actor_id)
    link = (
        await session.execute(
            select(ProjectShareLink).where(
                ProjectShareLink.id == link_id,
                ProjectShareLink.project_id == project_id,
                ProjectShareLink.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise ShareLinkNotFoundError()
    await _take_back(session, link)
