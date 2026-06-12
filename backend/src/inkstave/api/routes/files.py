"""Binary file upload/download routes (spec 14), scoped to an owned project."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile, status
from fastapi.responses import StreamingResponse

from inkstave.authorization.capabilities import Capability
from inkstave.authorization.dependencies import require_capability
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_object_store
from inkstave.errors import ErrorEnvelope
from inkstave.schemas.file import FileRead
from inkstave.security.rate_limit import rate_limit_named
from inkstave.security.uploads import sanitize_filename
from inkstave.services import file_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.db.models.file import File
    from inkstave.db.models.project import Project
    from inkstave.storage.base import ObjectStore

router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorEnvelope},
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ErrorEnvelope},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorEnvelope},
}

read_access = require_capability(Capability.FILE_READ)
write_access = require_capability(Capability.FILE_WRITE)


async def _read(session: AsyncSession, file_row: File) -> FileRead:
    # ``file_row.entity`` is eager-loaded by the file_service fetch (spec 99 #6.1),
    # so reading the name issues no standalone TreeEntity SELECT.
    return FileRead(
        entity_id=file_row.entity_id,
        project_id=file_row.project_id,
        name=file_row.entity.name,
        content_type=file_row.content_type,
        size_bytes=file_row.size_bytes,
        checksum_sha256=file_row.checksum_sha256,
        original_filename=file_row.original_filename,
        created_at=file_row.created_at,
        updated_at=file_row.updated_at,
    )


def _sanitize_header_filename(name: str) -> str:
    return name.replace('"', "").replace("\n", "").replace("\r", "")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=FileRead,
    summary="Upload a binary file",
    responses=_ERRORS,
    dependencies=[Depends(rate_limit_named("upload"))],
)
async def upload_file(
    file: UploadFile,
    parent_id: Annotated[UUID | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    project: Project = Depends(write_access),
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
) -> FileRead:
    # Per spec 52 §5.2.5, traversal/path components (e.g. ``../evil``) are *stripped*
    # to a safe basename here, not rejected with 422 as the original spec-14 AC5 asked.
    # A sanitized name that no longer carries an allowed extension is then rejected
    # downstream (415), and nothing is ever written to storage for it.
    effective_name = sanitize_filename(name or file.filename or "file")
    file_row = await file_service.upload_file(
        session,
        store,
        project.id,
        parent_id,
        effective_name,
        file.read,
        file.content_type,
        file.filename,
    )
    return await _read(session, file_row)


@router.get(
    "/{entity_id}",
    response_model=FileRead,
    summary="Get a file's metadata",
    responses=_ERRORS,
)
async def get_file(
    entity_id: UUID,
    project: Project = Depends(read_access),
    session: AsyncSession = Depends(get_db_session),
) -> FileRead:
    file_row = await file_service.get_file(session, project.id, entity_id)
    return await _read(session, file_row)


@router.get(
    "/{entity_id}/content",
    summary="Download a file's bytes",
    responses=_ERRORS,
)
async def download_file(
    entity_id: UUID,
    project: Project = Depends(read_access),
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
) -> StreamingResponse:
    file_row, stream = await file_service.open_file_content(session, store, project.id, entity_id)
    filename = _sanitize_header_filename(file_row.entity.name)
    headers = {
        "Content-Length": str(file_row.size_bytes),
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    return StreamingResponse(stream, media_type=file_row.content_type, headers=headers)


@router.delete(
    "/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a file (entity + blob)",
    responses=_ERRORS,
)
async def delete_file(
    entity_id: UUID,
    project: Project = Depends(write_access),
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
) -> None:
    await file_service.delete_file(session, store, project.id, entity_id)
