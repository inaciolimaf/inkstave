"""Collaborators & sharing routes (spec 33).

`/projects/{id}/members` and `/projects/{id}/invites` are project-scoped (owner or
member, per route). The token-based accept/decline/preview live under `/invites`.
All routes require authentication. Role *enforcement* elsewhere is spec 34.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from inkstave.auth.dependencies import get_current_user
from inkstave.db.models.project import Project
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_email_enqueuer, get_settings_dep
from inkstave.errors import ErrorEnvelope
from inkstave.notifications.invite_hook import notify_invite
from inkstave.schemas.sharing import (
    AcceptResponse,
    InviteCreate,
    InviteCreated,
    InvitePreview,
    InviteRead,
    MemberRead,
    MemberRoleUpdate,
    TransferRequest,
)
from inkstave.services import sharing as sharing_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.db.models.user import User
    from inkstave.mailer.enqueuer import EmailEnqueuer

router = APIRouter(prefix="/projects", tags=["sharing"])
invites_router = APIRouter(prefix="/invites", tags=["sharing"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}


def _member_read(info: sharing_service.MemberInfo) -> MemberRead:
    return MemberRead(
        user_id=info.user_id,
        name=info.name,
        email=info.email,
        role=info.role,
        status=info.status,
    )


# --- members --------------------------------------------------------------- #


@router.get("/{project_id}/members", response_model=list[MemberRead], responses=_NOT_FOUND)
async def list_members(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemberRead]:
    members = await sharing_service.list_members(session, project_id, user.id)
    return [_member_read(m) for m in members]


@router.patch("/{project_id}/members/{user_id}", response_model=MemberRead, responses=_NOT_FOUND)
async def change_member_role(
    project_id: UUID,
    user_id: UUID,
    data: MemberRoleUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemberRead:
    member = await sharing_service.change_role(session, project_id, user.id, user_id, data.role)
    return _member_read(member)


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
)
async def remove_member(
    project_id: UUID,
    user_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await sharing_service.remove_member(session, project_id, user.id, user_id)


@router.post("/{project_id}/members/transfer", response_model=MemberRead, responses=_NOT_FOUND)
async def transfer_ownership(
    project_id: UUID,
    data: TransferRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemberRead:
    member = await sharing_service.transfer_ownership(session, project_id, user.id, data.to_user_id)
    return _member_read(member)


# --- invites (owner) ------------------------------------------------------- #


@router.get("/{project_id}/invites", response_model=list[InviteRead], responses=_NOT_FOUND)
async def list_invites(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[InviteRead]:
    invites = await sharing_service.list_invites(session, project_id, user.id)
    return [InviteRead.model_validate(i) for i in invites]


@router.post(
    "/{project_id}/invites",
    status_code=status.HTTP_201_CREATED,
    response_model=InviteCreated,
    responses=_NOT_FOUND,
)
async def create_invite(
    project_id: UUID,
    data: InviteCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    enqueuer: EmailEnqueuer = Depends(get_email_enqueuer),
) -> InviteCreated:
    invite, raw_token = await sharing_service.create_invite(
        session, project_id, user.id, data.email, data.role, ttl_days=settings.invite_ttl_days
    )
    project_name = await session.scalar(select(Project.name).where(Project.id == project_id))
    # Spec-39 hook: in-app notification (if the invitee has an account) + invite email.
    await notify_invite(
        session,
        enqueuer,
        settings,
        invite=invite,
        raw_token=raw_token,
        project_name=project_name or "the project",
        inviter_name=user.display_name,
    )
    return InviteCreated(**InviteRead.model_validate(invite).model_dump(), token=raw_token)


@router.delete(
    "/{project_id}/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
)
async def revoke_invite(
    project_id: UUID,
    invite_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await sharing_service.revoke_invite(session, project_id, user.id, invite_id)


# --- token-based accept / decline / preview -------------------------------- #


@invites_router.get("/{token}", response_model=InvitePreview, responses=_NOT_FOUND)
async def get_invite_preview(
    token: str,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> InvitePreview:
    invite, project, inviter = await sharing_service.get_invite_preview(session, token)
    return InvitePreview(
        project_id=project.id,
        project_name=project.name,
        inviter_name=inviter.display_name,
        role=invite.role,
        email=invite.email,
    )


@invites_router.post("/{token}/accept", response_model=AcceptResponse, responses=_NOT_FOUND)
async def accept_invite(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AcceptResponse:
    project_id, role = await sharing_service.accept_invite(session, token, user)
    return AcceptResponse(project_id=project_id, role=role)


@invites_router.post(
    "/{token}/decline", status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND
)
async def decline_invite(
    token: str,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await sharing_service.decline_invite(session, token)
