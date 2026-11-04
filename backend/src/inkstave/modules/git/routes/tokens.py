"""Git access token routes (spec 121 §5.1). They take the session token: a Git token cannot manage tokens."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from inkstave.core.config.settings import Settings
from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.deps import get_settings_dep
from inkstave.modules.auth import User, get_current_user
from inkstave.modules.git.auth.tokens import create_token, list_tokens, revoke_token
from inkstave.modules.git.errors import GitDisabledError
from inkstave.modules.git.schemas import GitTokenCreate, GitTokenCreated, GitTokenList, GitTokenRead

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/git/tokens", tags=["git"])


def _require_enabled(settings: Settings) -> None:
    if not settings.git_enabled:
        raise GitDisabledError()


@router.post("", status_code=201, response_model=GitTokenCreated, summary="Create a Git access token")
async def create(
    body: GitTokenCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    settings: Settings = Depends(get_settings_dep),
) -> GitTokenCreated:
    _require_enabled(settings)
    issued = await create_token(session, user.id, body.name, body.expires_at)
    return GitTokenCreated(**GitTokenRead.model_validate(issued.row).model_dump(), token=issued.raw)


@router.get("", response_model=GitTokenList, summary="List the caller's Git access tokens")
async def list_all(
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    settings: Settings = Depends(get_settings_dep),
) -> GitTokenList:
    _require_enabled(settings)
    rows = await list_tokens(session, user.id)
    return GitTokenList(tokens=[GitTokenRead.model_validate(row) for row in rows])


@router.delete("/{token_id}", status_code=204, summary="Revoke a Git access token")
async def revoke(
    token_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    _require_enabled(settings)
    await revoke_token(session, user.id, token_id)
    return Response(status_code=204)
