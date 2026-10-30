"""Project CRUD routes (spec 11). All routes require authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from inkstave.core.db.session import get_db_session
from inkstave.core.deps import get_redis, get_settings_dep
from inkstave.core.errors import ErrorEnvelope
from inkstave.infra.cache import RedisCache, project_meta_key
from inkstave.infra.deps import get_object_store
from inkstave.modules.auth import get_current_user
from inkstave.modules.collab import flush_open_project_docs
from inkstave.modules.compile import OutputRepository, OutputStore
from inkstave.modules.projects.access.capabilities import Capability, capabilities_for
from inkstave.modules.projects.access.deps import require_capability
from inkstave.modules.projects.access.service import role_for
from inkstave.modules.projects.catalog import service as project_service
from inkstave.modules.projects.catalog.service import ProjectNotFoundError
from inkstave.modules.projects.schemas.project import (
    PermissionsRead,
    ProjectCreate,
    ProjectList,
    ProjectRead,
    ProjectRename,
)
from inkstave.modules.projects.transfer import export as export_service

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings
    from inkstave.infra.storage.base import ObjectStore
    from inkstave.modules.auth import User
    from inkstave.modules.projects.models.project import Project

router = APIRouter(prefix="/projects", tags=["projects"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}

read_access = require_capability(Capability.PROJECT_READ)
write_access = require_capability(Capability.PROJECT_WRITE)
delete_access = require_capability(Capability.PROJECT_DELETE)
download_access = require_capability(Capability.PROJECT_DOWNLOAD)

_EXPORT_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorEnvelope},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectRead,
    summary="Create a project",
)
async def create_project(
    data: ProjectCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectRead:
    project = await project_service.create_project(session, user.id, data.name)
    return ProjectRead.model_validate(project)


@router.get("", response_model=ProjectList, summary="List the caller's projects")
async def list_projects(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectList:
    items, total = await project_service.list_projects(session, user.id, limit, offset)
    return ProjectList(items=[ProjectRead.model_validate(p) for p in items], total=total)


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project",
    responses=_NOT_FOUND,
)
async def get_project(
    project: Project = Depends(read_access),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> ProjectRead:
    # Any active member may read (spec 34); the dependency authorizes + loads it.
    # Post-authz project metadata is cached with a short TTL (spec 53); reads served
    # from Redis on a hit, invalidated on rename/delete below.
    cache = RedisCache(redis, settings)
    key = project_meta_key(project.id)
    cached = await cache.get_json(key)
    if cached is not None:
        return ProjectRead.model_validate(cached)
    out = ProjectRead.model_validate(project)
    await cache.set_json(key, out.model_dump(mode="json"))
    return out


@router.get(
    "/{project_id}/permissions",
    response_model=PermissionsRead,
    summary="The caller's role + capabilities on a project",
    responses=_NOT_FOUND,
)
async def get_permissions(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> PermissionsRead:
    role = await role_for(session, user.id, project_id)
    if role is None:
        raise ProjectNotFoundError()  # 404 — non-member / missing
    caps = capabilities_for(role, compile_for_viewers=settings.compile_allowed_for_viewers)
    return PermissionsRead(role=role, capabilities=sorted(c.value for c in caps))


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Rename a project",
    responses=_NOT_FOUND,
)
async def rename_project(
    project_id: UUID,
    data: ProjectRename,
    _project: Project = Depends(write_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> ProjectRead:
    project = await project_service.rename_project(session, user.id, project_id, data.name)
    await RedisCache(redis, settings).invalidate(project_meta_key(project_id))
    return ProjectRead.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a project",
    responses=_NOT_FOUND,
)
async def delete_project(
    project_id: UUID,
    _project: Project = Depends(delete_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> None:
    await project_service.soft_delete_project(session, user.id, project_id)
    await RedisCache(redis, settings).invalidate(project_meta_key(project_id))
    # Soft-delete doesn't FK-cascade; sweep the project's compile-output bytes.
    output_store = OutputStore(storage=store, repo=OutputRepository(session), settings=settings)
    await output_store.delete_for_project(project_id)


@router.get(
    "/{project_id}/export.zip",
    summary="Download the whole project as a .zip",
    responses=_EXPORT_ERRORS,
)
async def export_project_zip(
    request: Request,
    project: Project = Depends(download_access),
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
) -> StreamingResponse:
    # Flush live CRDT rooms so text docs export their current content (spec 28/31),
    # exactly as the compile enqueue does.
    await flush_open_project_docs(getattr(request.app.state, "collab", None), session, project.id)
    # Build the deterministic plan (and enforce the size cap) BEFORE streaming so a
    # 413 is returned cleanly rather than mid-stream.
    plan = await export_service.build_export_plan(session, project.id, settings)
    headers = {
        "Content-Disposition": export_service.content_disposition(
            export_service.zip_filename_for(project.name)
        )
    }
    return StreamingResponse(
        export_service.stream_project_zip(plan, store, session, settings),
        media_type="application/zip",
        headers=headers,
    )
