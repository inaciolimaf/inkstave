"""The Git Smart HTTP routes (spec 121 §5.3). HTTP only: authorization and the work live in the module.

``git clone https://<host>/api/v1/git/projects/<project_id>.git`` works with a token as the password. The dumb
protocol is not served, so an ``info/refs`` without ``service`` is a 404.
"""

from __future__ import annotations

import zlib
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inkstave.core.config.settings import Settings
from inkstave.core.db.session import UNIT_OF_WORK, get_session_factory
from inkstave.core.deps import get_redis, get_settings_dep
from inkstave.core.errors import NotFoundError
from inkstave.infra.deps import get_object_store
from inkstave.modules.git.auth.access import READ_CAPABILITIES, WRITE_CAPABILITIES, authorize_git
from inkstave.modules.git.errors import GitBodyTooLargeError, GitUnsupportedMediaError
from inkstave.modules.git.repo.protocol import SERVICES
from inkstave.modules.git.service import GitDeps, advertise_refs, receive_pack, upload_pack

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from redis.asyncio import Redis

    from inkstave.infra.storage.base import ObjectStore

router = APIRouter(prefix="/git/projects/{project_id}.git", tags=["git"])

_NO_CACHE = {"Cache-Control": "no-cache, max-age=0, must-revalidate", "Pragma": "no-cache"}
_UPLOAD_REQUEST = "application/x-git-upload-pack-request"
_RECEIVE_REQUEST = "application/x-git-receive-pack-request"
_CHUNK_BYTES = 65_536


def _git_deps(
    request: Request,
    factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> GitDeps:
    return GitDeps(
        factory=factory,
        store=store,
        collab=getattr(request.app.state, "collab", None),
        settings=settings,
        redis=redis,
    )


def _require_content_type(request: Request, expected: str) -> None:
    received = (request.headers.get("content-type") or "").split(";")[0].strip()
    if received != expected:
        raise GitUnsupportedMediaError(expected)


async def _request_body(request: Request, limit: int) -> bytes:
    """The request body, gunzipped when git compressed it (git does so for large fetches)."""
    raw = await request.body()
    if request.headers.get("content-encoding", "").lower() != "gzip":
        return raw
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    body = inflater.decompress(raw, limit + 1)
    if len(body) > limit or inflater.unconsumed_tail:
        raise GitBodyTooLargeError()
    return body


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    for start in range(0, len(data), _CHUNK_BYTES):
        yield data[start : start + _CHUNK_BYTES]


@router.get("/info/refs", summary="Git discovery: the refs for a service")
async def info_refs(
    project_id: UUID,
    request: Request,
    service: str | None = Query(default=None),
    session: AsyncSession = UNIT_OF_WORK,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    deps: GitDeps = Depends(_git_deps),
) -> Response:
    if service not in SERVICES:
        raise NotFoundError("Only the smart protocol is served.")
    needed = READ_CAPABILITIES if service == "git-upload-pack" else WRITE_CAPABILITIES
    await authorize_git(
        request=request,
        session=session,
        redis=redis,
        settings=settings,
        project_id=project_id,
        needed=needed,
    )
    body = await advertise_refs(deps, project_id, service)
    return Response(
        content=body,
        media_type=f"application/x-{service}-advertisement",
        headers=_NO_CACHE,
    )


@router.post("/git-upload-pack", summary="Git fetch: pack negotiation and transfer")
async def upload_pack_route(
    project_id: UUID,
    request: Request,
    session: AsyncSession = UNIT_OF_WORK,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    deps: GitDeps = Depends(_git_deps),
) -> StreamingResponse:
    _require_content_type(request, _UPLOAD_REQUEST)
    await authorize_git(
        request=request,
        session=session,
        redis=redis,
        settings=settings,
        project_id=project_id,
        needed=READ_CAPABILITIES,
    )
    body = await _request_body(request, settings.max_upload_bytes)
    data = await upload_pack(deps, project_id, body)
    return StreamingResponse(
        _chunks(data),
        media_type="application/x-git-upload-pack-result",
        headers=_NO_CACHE,
    )


@router.post("/git-receive-pack", summary="Git push: apply a pushed main branch")
async def receive_pack_route(
    project_id: UUID,
    request: Request,
    session: AsyncSession = UNIT_OF_WORK,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    deps: GitDeps = Depends(_git_deps),
) -> Response:
    _require_content_type(request, _RECEIVE_REQUEST)
    caller = await authorize_git(
        request=request,
        session=session,
        redis=redis,
        settings=settings,
        project_id=project_id,
        needed=WRITE_CAPABILITIES,
    )
    body = await _request_body(request, settings.git_max_push_bytes)
    data = await receive_pack(deps, project_id, body, caller)
    return Response(content=data, media_type="application/x-git-receive-pack-result", headers=_NO_CACHE)
