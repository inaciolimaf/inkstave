"""Project import from a ``.zip`` archive (spec 101).

A multipart upload endpoint that **always** creates a NEW project and hands the
archive to an ARQ background job; plus poll + SSE status endpoints mirroring the
spec-22 compile status surface.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, UploadFile, status
from fastapi.responses import StreamingResponse

from inkstave.api.routes.compile_helpers import _sse_user
from inkstave.auth.dependencies import get_current_user
from inkstave.authorization.capabilities import Capability
from inkstave.authorization.dependencies import require_capability
from inkstave.authorization.service import role_for
from inkstave.db.session import get_db_session
from inkstave.dependencies import (
    get_import_enqueuer,
    get_object_store,
    get_redis,
    get_settings_dep,
)
from inkstave.errors import ErrorEnvelope, NotFoundError
from inkstave.schemas.project_import import ProjectImportRead
from inkstave.security.rate_limit import rate_limit_named
from inkstave.security.uploads import extension_of, sanitize_filename
from inkstave.services import project as project_service
from inkstave.services.file_service import FileTooLargeError, UnsupportedMediaTypeError
from inkstave.services.import_enqueuer import ImportEnqueuer
from inkstave.services.import_repository import ProjectImportRepository
from inkstave.services.import_stream import sse_stream
from inkstave.services.project import ProjectNotFoundError

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.db.models.project import Project
    from inkstave.db.models.project_import import ProjectImport
    from inkstave.db.models.user import User
    from inkstave.storage.base import ObjectStore

# Import is not project-scoped (it creates the project), so it lives on its own
# router. The status routes ARE project-scoped and reuse the capability guard.
router = APIRouter(prefix="/projects", tags=["project-import"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorEnvelope},
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ErrorEnvelope},
}

_ZIP_CONTENT_TYPES = {"application/zip", "application/x-zip-compressed"}
_ZIP_MAGIC = b"PK\x03\x04"

read_access = require_capability(Capability.PROJECT_READ)


class ImportNotFoundError(NotFoundError):
    error_type = "import_not_found"

    def __init__(self) -> None:
        super().__init__("Import not found.")


def _looks_like_zip(content_type: str | None, head: bytes) -> bool:
    ct = (content_type or "").lower().split(";")[0].strip()
    if ct in _ZIP_CONTENT_TYPES:
        return True
    # A generic/empty declared type is accepted only with the PK zip magic bytes.
    return head.startswith(_ZIP_MAGIC)


def _effective_name(name: str | None, filename: str | None) -> str:
    candidate = (name or "").strip()
    if candidate:
        return candidate[:255]
    if filename:
        stem = sanitize_filename(os.path.splitext(filename)[0])
        if stem and stem != "file":
            return stem
    return "Imported project"


@router.post(
    "/import",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ProjectImportRead,
    summary="Import a project from a .zip archive",
    responses=_ERRORS,
    dependencies=[Depends(rate_limit_named("upload"))],
)
async def import_project(
    file: UploadFile,
    name: Annotated[str | None, Form()] = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    store: ObjectStore = Depends(get_object_store),
    enqueuer: ImportEnqueuer = Depends(get_import_enqueuer),
) -> ProjectImportRead:
    # Cheap synchronous validation before any heavy work (no full read).
    if extension_of(file.filename or "") != ".zip":
        raise UnsupportedMediaTypeError()

    chunk_size = settings.storage_stream_chunk_bytes
    head = await file.read(chunk_size)
    if not _looks_like_zip(file.content_type, head):
        raise UnsupportedMediaTypeError()

    source_key = f"imports/{uuid4()}/source.zip"
    total = {"n": 0}

    async def body() -> Any:
        chunk = head
        while chunk:
            total["n"] += len(chunk)
            if total["n"] > settings.import_max_zip_bytes:
                raise FileTooLargeError()
            yield chunk
            chunk = await file.read(chunk_size)

    try:
        await store.put(source_key, body(), content_type="application/zip")
    except FileTooLargeError:
        # No orphan staged blob (AC6): the partial write is best-effort removed.
        await store.delete(source_key)
        raise

    # One transaction: create the NEW project, the import row, then enqueue.
    try:
        project = await project_service.create_project(
            session, user.id, _effective_name(name, file.filename)
        )
        repo = ProjectImportRepository(session)
        row = await repo.create(
            project_id=project.id,
            requested_by=user.id,
            source_key=source_key,
            source_bytes=total["n"],
            original_filename=sanitize_filename(file.filename) if file.filename else None,
        )
        job_id = await enqueuer.enqueue(row.id)
        if job_id is not None:
            await repo.update(row, job_id=job_id)
    except Exception:
        await store.delete(source_key)  # best-effort: no orphan blob on a DB failure
        raise
    return ProjectImportRead.model_validate(row)


@router.get(
    "/{project_id}/import",
    response_model=ProjectImportRead,
    summary="Get the latest import for a project",
    responses=_ERRORS,
)
async def get_latest_import(
    project: Project = Depends(read_access),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectImportRead:
    row = await ProjectImportRepository(session).get_latest(project.id)
    if row is None:
        raise ImportNotFoundError()
    return ProjectImportRead.model_validate(row)


@router.get(
    "/{project_id}/import/{import_id}",
    response_model=ProjectImportRead,
    summary="Get an import's status",
    responses=_ERRORS,
)
async def get_import(
    import_id: UUID,
    project: Project = Depends(read_access),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectImportRead:
    row = await ProjectImportRepository(session).get(project.id, import_id)
    if row is None:
        raise ImportNotFoundError()
    return ProjectImportRead.model_validate(row)


@router.get(
    "/{project_id}/import/{import_id}/events",
    summary="Live import status (Server-Sent Events)",
    responses=_ERRORS,
)
async def import_events(
    import_id: UUID,
    project_id: UUID,
    user: User = Depends(_sse_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    # SSE uses a query-param token (EventSource can't set headers); authorize inline.
    if await role_for(session, user.id, project_id) is None:
        raise ProjectNotFoundError()  # 404 — non-member / missing project
    repo = ProjectImportRepository(session)
    if await repo.get(project_id, import_id) is None:
        raise ImportNotFoundError()

    async def snapshot() -> dict[str, Any] | None:
        row: ProjectImport | None = await repo.get(project_id, import_id)
        return ProjectImportRead.model_validate(row).model_dump(mode="json") if row else None

    return StreamingResponse(
        sse_stream(redis, import_id, snapshot, settings.compile_sse_keepalive_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
