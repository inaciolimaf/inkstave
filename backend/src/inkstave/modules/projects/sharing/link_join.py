"""Opening a share link as a signed-in user (spec 116): preview, then join or upgrade.

A link never lowers a role. A viewer who opens the edit link becomes an editor and remembers the
viewer role; an editor who opens the view link stays an editor. Joining creates an active membership
with the link's role when the user has none, or re-activates a ``left`` one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.modules.auth import User, hash_token
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.modules.projects.models.project import Project
from inkstave.modules.projects.models.share_link import ProjectShareLink
from inkstave.modules.projects.sharing.common import detach_from_link, membership_of
from inkstave.modules.projects.sharing.errors import ShareLinkNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_RANK: dict[str, int] = {
    MembershipRole.viewer: 1,
    MembershipRole.editor: 2,
    MembershipRole.owner: 3,
}


@dataclass(frozen=True)
class SharePreview:
    link: ProjectShareLink
    project: Project
    owner: User
    already_member_role: str | None


async def _live_link(session: AsyncSession, raw_token: str) -> tuple[ProjectShareLink, Project]:
    """The active link and its live project. Unknown, revoked and dead-project links look the same."""
    row = (
        await session.execute(
            select(ProjectShareLink, Project)
            .join(Project, Project.id == ProjectShareLink.project_id)
            .where(
                ProjectShareLink.token_hash == hash_token(raw_token),
                ProjectShareLink.revoked_at.is_(None),
                Project.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise ShareLinkNotFoundError()
    return row[0], row[1]


async def _active_role(session: AsyncSession, project_id: UUID, user_id: UUID) -> str | None:
    member = await membership_of(session, project_id, user_id)
    if member is None or member.status != MembershipStatus.active:
        return None
    return member.role


async def get_share_link_preview(session: AsyncSession, raw_token: str, actor_id: UUID) -> SharePreview:
    link, project = await _live_link(session, raw_token)
    owner = (await session.execute(select(User).where(User.id == project.owner_id))).scalar_one()
    return SharePreview(
        link=link,
        project=project,
        owner=owner,
        already_member_role=await _active_role(session, project.id, actor_id),
    )


def _grant(member: ProjectMembership, link: ProjectShareLink) -> None:
    """Create or re-activate a membership with the link's role; the link is remembered."""
    member.role = link.role
    member.status = MembershipStatus.active
    member.via_link_id = link.id
    member.role_before_link = None


def _upgrade(member: ProjectMembership, link: ProjectShareLink) -> None:
    """Raise an active member to the link's role, remembering the role to return to. Never lowers."""
    if _RANK[member.role] >= _RANK[link.role]:
        return
    member.role_before_link = member.role
    member.role = link.role
    member.via_link_id = link.id


async def join_share_link(session: AsyncSession, raw_token: str, actor_id: UUID) -> ProjectMembership:
    link, project = await _live_link(session, raw_token)
    member = await membership_of(session, project.id, actor_id)
    if member is None:
        member = ProjectMembership(project_id=project.id, user_id=actor_id)
        session.add(member)
        _grant(member, link)
    elif member.status != MembershipStatus.active:
        detach_from_link(member)
        _grant(member, link)
    else:
        _upgrade(member, link)
    await session.flush()
    return member
