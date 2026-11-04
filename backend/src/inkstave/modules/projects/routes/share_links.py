"""Share-link routes (spec 116).

The owner manages a project's links under `/projects/{project_id}/share-links`. Anyone signed in
previews and joins a link under `/share-links/{token}`, rate limited per user. Owner checks happen
in the sharing service (`require_owner`), which is why these routes are on the guard audit list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.deps import get_settings_dep
from inkstave.core.errors import ErrorEnvelope
from inkstave.modules.auth import get_current_user, rate_limit_named
from inkstave.modules.projects import sharing as sharing_service
from inkstave.modules.projects.schemas.sharing import (
    ShareLinkCreate,
    ShareLinkCreated,
    ShareLinkJoined,
    ShareLinkRead,
    SharePreview,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings
    from inkstave.modules.auth import User

router = APIRouter(prefix="/projects", tags=["sharing"])
links_router = APIRouter(prefix="/share-links", tags=["sharing"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}


def _share_url(settings: Settings, token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/join/{token}"


@router.get("/{project_id}/share-links", response_model=list[ShareLinkRead], responses=_NOT_FOUND)
async def list_share_links(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> list[ShareLinkRead]:
    links = await sharing_service.list_share_links(session, project_id, user.id)
    return [ShareLinkRead.model_validate(link) for link in links]


@router.post(
    "/{project_id}/share-links",
    status_code=status.HTTP_201_CREATED,
    response_model=ShareLinkCreated,
    responses=_NOT_FOUND,
)
async def create_share_link(
    project_id: UUID,
    data: ShareLinkCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    settings: Settings = Depends(get_settings_dep),
) -> ShareLinkCreated:
    link, raw_token = await sharing_service.create_share_link(session, project_id, user.id, data.role)
    return ShareLinkCreated(
        **ShareLinkRead.model_validate(link).model_dump(),
        token=raw_token,
        url=_share_url(settings, raw_token),
    )


@router.delete(
    "/{project_id}/share-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
)
async def revoke_share_link(
    project_id: UUID,
    link_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> None:
    await sharing_service.revoke_share_link(session, project_id, user.id, link_id)


@links_router.get(
    "/{token}",
    response_model=SharePreview,
    responses=_NOT_FOUND,
    dependencies=[Depends(rate_limit_named("share_link"))],
)
async def preview_share_link(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> SharePreview:
    preview = await sharing_service.get_share_link_preview(session, token, user.id)
    return SharePreview(
        project_id=preview.project.id,
        project_name=preview.project.name,
        owner_name=preview.owner.display_name,
        role=preview.link.role,
        already_member_role=preview.already_member_role,
    )


@links_router.post(
    "/{token}/join",
    response_model=ShareLinkJoined,
    responses=_NOT_FOUND,
    dependencies=[Depends(rate_limit_named("share_link"))],
)
async def join_share_link(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> ShareLinkJoined:
    member = await sharing_service.join_share_link(session, token, user.id)
    return ShareLinkJoined(project_id=member.project_id, role=member.role)
