"""Project CRUD routes (spec 11). All routes require authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from inkstave.auth.dependencies import get_current_user
from inkstave.compile.output_repository import OutputRepository
from inkstave.compile.outputs import OutputStore
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_object_store, get_settings_dep
from inkstave.errors import ErrorEnvelope
from inkstave.schemas.project import ProjectCreate, ProjectList, ProjectRead, ProjectRename
from inkstave.services import project as project_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.db.models.user import User
    from inkstave.storage.base import ObjectStore

router = APIRouter(prefix="/projects", tags=["projects"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}


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
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectRead:
    project = await project_service.get_owned_project(session, user.id, project_id)
    return ProjectRead.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Rename a project",
    responses=_NOT_FOUND,
)
async def rename_project(
    project_id: UUID,
    data: ProjectRename,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectRead:
    project = await project_service.rename_project(session, user.id, project_id, data.name)
    return ProjectRead.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a project",
    responses=_NOT_FOUND,
)
async def delete_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    await project_service.soft_delete_project(session, user.id, project_id)
    # Soft-delete doesn't FK-cascade; sweep the project's compile-output bytes.
    output_store = OutputStore(storage=store, repo=OutputRepository(session), settings=settings)
    await output_store.delete_for_project(project_id)
