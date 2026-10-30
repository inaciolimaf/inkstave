"""History API routes (spec 37): versions, updates, diff, restore, labels."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.deps import get_settings_dep
from inkstave.core.errors import BadRequestError, ErrorEnvelope
from inkstave.infra.storage.factory import get_object_store
from inkstave.modules.auth import get_current_user
from inkstave.modules.history.schemas import (
    LabelCreate,
    LabelRead,
    ProjectLabelCreate,
    ProjectRestoreRequest,
    ProjectRestoreResponse,
    RestoreRequest,
    RestoreResponse,
    UpdatesResponse,
    VersionsResponse,
)
from inkstave.modules.history.versions import labels as labels_service
from inkstave.modules.history.versions.read import (
    doc_belongs_to_project,
    get_diff,
    list_updates,
    list_versions,
)
from inkstave.modules.history.versions.restore import RestoreScope, restore_document, restore_project
from inkstave.modules.projects import Capability, ProjectNotFoundError, require_capability

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings
    from inkstave.infra.storage.base import ObjectStore
    from inkstave.modules.auth import User
    from inkstave.modules.collab.ws.components import CollabComponents
    from inkstave.modules.projects import Project

router = APIRouter(prefix="/projects/{project_id}", tags=["history"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}

read_access = require_capability(Capability.PROJECT_READ)
write_access = require_capability(Capability.DOC_WRITE)


def _store(settings: Settings = Depends(get_settings_dep)) -> ObjectStore:
    return get_object_store(settings)


def _components(request: Request) -> CollabComponents | None:
    return getattr(request.app.state, "collab", None)


async def _verify_doc(session: AsyncSession, project_id: UUID, doc_id: UUID) -> None:
    """404 (anti-enumeration) if the doc is not a document of this project."""
    if not await doc_belongs_to_project(session, project_id, doc_id):
        raise ProjectNotFoundError()


# --- list / diff (any member) ---------------------------------------------- #


@router.get("/docs/{doc_id}/history/versions", response_model=VersionsResponse, responses=_ERRORS)
async def get_versions(
    doc_id: UUID,
    before: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1),
    project: Project = Depends(read_access),
    session: AsyncSession = UNIT_OF_WORK,
    settings: Settings = Depends(get_settings_dep),
) -> VersionsResponse:
    await _verify_doc(session, project.id, doc_id)
    capped = min(limit, settings.history_versions_page_max)
    return await list_versions(session, doc_id, before=before, limit=capped)


@router.get("/docs/{doc_id}/history/updates", response_model=UpdatesResponse, responses=_ERRORS)
async def get_updates(
    doc_id: UUID,
    from_: int | None = Query(None, alias="from", ge=1),
    to: int | None = Query(None, ge=1),
    project: Project = Depends(read_access),
    session: AsyncSession = UNIT_OF_WORK,
) -> UpdatesResponse:
    await _verify_doc(session, project.id, doc_id)
    if from_ is not None and to is not None and from_ > to:
        raise BadRequestError("`from` must not exceed `to`.")
    return await list_updates(session, doc_id, from_v=from_, to_v=to)


@router.get("/docs/{doc_id}/history/diff", responses=_ERRORS)
async def get_history_diff(
    doc_id: UUID,
    from_: int = Query(..., alias="from", ge=1),
    to: str = Query(...),
    project: Project = Depends(read_access),
    session: AsyncSession = UNIT_OF_WORK,
    settings: Settings = Depends(get_settings_dep),
    store: ObjectStore = Depends(_store),
) -> JSONResponse:
    await _verify_doc(session, project.id, doc_id)
    if to == "current":
        target: int | str = "current"
    else:
        try:
            target = int(to)
        except ValueError as exc:
            raise BadRequestError("`to` must be a version number or 'current'.") from exc
    result = await get_diff(session, store, settings, doc_id, from_v=from_, to=target)
    code = status.HTTP_413_CONTENT_TOO_LARGE if result.too_large else status.HTTP_200_OK
    return JSONResponse(result.model_dump(by_alias=True), status_code=code)


# --- restore (editor / owner) ---------------------------------------------- #


@router.post("/docs/{doc_id}/history/restore", response_model=RestoreResponse, responses=_ERRORS)
async def restore_doc(
    request: Request,
    doc_id: UUID,
    body: RestoreRequest,
    project: Project = Depends(write_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    store: ObjectStore = Depends(_store),
) -> RestoreResponse:
    await _verify_doc(session, project.id, doc_id)
    return await restore_document(
        session,
        _components(request),
        store,
        scope=RestoreScope(project.id, doc_id, user.id),
        target_version=body.version,
        label_name=body.label_name,
    )


@router.post("/history/restore", response_model=ProjectRestoreResponse, responses=_ERRORS)
async def restore_whole_project(
    request: Request,
    body: ProjectRestoreRequest,
    project: Project = Depends(write_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    store: ObjectStore = Depends(_store),
) -> ProjectRestoreResponse:
    label = await labels_service.get_project_label(session, project_id=project.id, label_id=body.label_id)
    return await restore_project(
        session,
        _components(request),
        store,
        project_id=project.id,
        markers=label.payload or {},
        author_id=user.id,
    )


# --- labels CRUD ----------------------------------------------------------- #


@router.post(
    "/docs/{doc_id}/history/labels",
    status_code=status.HTTP_201_CREATED,
    response_model=LabelRead,
    responses=_ERRORS,
)
async def create_label(
    doc_id: UUID,
    body: LabelCreate,
    project: Project = Depends(write_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> LabelRead:
    await _verify_doc(session, project.id, doc_id)
    row = await labels_service.create_doc_label(
        session,
        project_id=project.id,
        doc_id=doc_id,
        version=body.version,
        name=body.name,
        created_by=user.id,
    )
    return LabelRead.model_validate(row)


@router.get("/docs/{doc_id}/history/labels", response_model=list[LabelRead], responses=_ERRORS)
async def get_labels(
    doc_id: UUID,
    project: Project = Depends(read_access),
    session: AsyncSession = UNIT_OF_WORK,
) -> list[LabelRead]:
    await _verify_doc(session, project.id, doc_id)
    return [
        LabelRead.model_validate(label) for label in await labels_service.list_doc_labels(session, doc_id)
    ]


@router.delete(
    "/docs/{doc_id}/history/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
)
async def delete_label(
    doc_id: UUID,
    label_id: UUID,
    project: Project = Depends(write_access),
    session: AsyncSession = UNIT_OF_WORK,
) -> None:
    await _verify_doc(session, project.id, doc_id)
    await labels_service.delete_doc_label(session, project_id=project.id, doc_id=doc_id, label_id=label_id)


@router.post(
    "/history/labels",
    status_code=status.HTTP_201_CREATED,
    response_model=LabelRead,
    responses=_ERRORS,
)
async def create_project_label(
    body: ProjectLabelCreate,
    project: Project = Depends(write_access),
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> LabelRead:
    row = await labels_service.create_project_label(
        session, project_id=project.id, name=body.name, created_by=user.id
    )
    return LabelRead.model_validate(row)


@router.get("/history/labels", response_model=list[LabelRead], responses=_ERRORS)
async def get_project_labels(
    project: Project = Depends(read_access),
    session: AsyncSession = UNIT_OF_WORK,
) -> list[LabelRead]:
    rows = await labels_service.list_project_labels(session, project.id)
    return [LabelRead.model_validate(label) for label in rows]


@router.delete(
    "/history/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
)
async def delete_project_label(
    label_id: UUID,
    project: Project = Depends(write_access),
    session: AsyncSession = UNIT_OF_WORK,
) -> None:
    await labels_service.delete_project_label(session, project_id=project.id, label_id=label_id)
