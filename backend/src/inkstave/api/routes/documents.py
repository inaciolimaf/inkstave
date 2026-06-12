"""Document content routes (spec 13), scoped to an owned project."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from inkstave.api.routes.tree import owned_project
from inkstave.db.session import get_db_session
from inkstave.errors import ErrorEnvelope
from inkstave.schemas.document import DocumentContentRead, DocumentContentReplace
from inkstave.services import document_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.db.models.project import Project

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorEnvelope},
}


@router.get(
    "/{entity_id}",
    response_model=DocumentContentRead,
    summary="Read a document's content",
    responses=_ERRORS,
)
async def get_content(
    entity_id: UUID,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentContentRead:
    document = await document_service.get_document(session, project.id, entity_id)
    return DocumentContentRead.model_validate(document)


@router.put(
    "/{entity_id}",
    response_model=DocumentContentRead,
    summary="Replace a document's content (optimistic, version-checked)",
    responses=_ERRORS,
)
async def replace_content(
    entity_id: UUID,
    data: DocumentContentReplace,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentContentRead:
    document = await document_service.replace_content(
        session, project.id, entity_id, data.content, data.base_version
    )
    return DocumentContentRead.model_validate(document)
