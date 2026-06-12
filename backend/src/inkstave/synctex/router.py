"""SyncTeX HTTP endpoints: forward (code->pdf) and inverse (pdf->code) (spec 26)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query, status

from inkstave.authorization.capabilities import Capability
from inkstave.authorization.dependencies import require_capability
from inkstave.compile.output_repository import OutputRepository
from inkstave.compile.outputs import OutputStore
from inkstave.compile.repository import CompileRepository
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_object_store, get_settings_dep
from inkstave.errors import ErrorEnvelope, NotFoundError
from inkstave.synctex.models import ForwardResult, InverseResult
from inkstave.synctex.service import SyncTexNotAvailable, SyncTexService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.db.models.project import Project
    from inkstave.storage.base import ObjectStore

router = APIRouter(prefix="/projects/{project_id}/synctex", tags=["synctex"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


class SyncTexUnavailableError(NotFoundError):
    """No synctex data for this compile — distinct from a no-match result."""

    error_type = "synctex_unavailable"

    def __init__(self) -> None:
        super().__init__("synctex_unavailable")


class SyncTexNoMatchError(NotFoundError):
    """Synctex data exists but no source/PDF location matched the query."""

    error_type = "synctex_no_match"

    def __init__(self) -> None:
        super().__init__("no_match")


# Read-only compile-output access: any active member (spec 34).
#
# Non-member -> 404 (NOT 403), by deliberate design. This is the Phase-2
# `require_capability` anti-enumeration pattern (per ADR 0026): a non-member must
# not be able to distinguish "project exists but you lack access" (403) from
# "no such project" (404), so both collapse to 404. This is a knowing deviation
# from spec 26 criterion 8 (which, as written, expects 403 for a non-member); we
# keep the 404 because returning 403 would leak project existence and weaken the
# security posture. The matching synctex integration test asserts 404 and cites
# this same rationale.
owned_project = require_capability(Capability.PROJECT_READ)


def get_synctex_service(
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
) -> SyncTexService:
    output_store = OutputStore(storage=store, repo=OutputRepository(session), settings=settings)
    return SyncTexService(
        repo=CompileRepository(session), output_store=output_store, settings=settings
    )


@router.get(
    "/code-to-pdf",
    response_model=ForwardResult,
    summary="Forward sync: source line -> PDF boxes",
    responses=_ERRORS,
)
async def code_to_pdf(
    project: Project = Depends(owned_project),
    file: str = Query(..., description="project-relative source path"),
    line: int = Query(..., ge=1, description="1-based source line"),
    column: int | None = Query(None, ge=1, description="1-based column (optional)"),
    compile_id: str | None = Query(None, description="defaults to latest successful compile"),
    service: SyncTexService = Depends(get_synctex_service),
) -> ForwardResult:
    try:
        result = await service.code_to_pdf(project.id, compile_id, file, line, column)
    except SyncTexNotAvailable as exc:
        raise SyncTexUnavailableError() from exc
    if not result.boxes:
        raise SyncTexNoMatchError()
    return result


@router.get(
    "/pdf-to-code",
    response_model=InverseResult,
    summary="Inverse sync: PDF point -> source location",
    responses=_ERRORS,
)
async def pdf_to_code(
    project: Project = Depends(owned_project),
    page: int = Query(..., ge=1, description="1-based PDF page"),
    h: float = Query(..., description="horizontal position, PDF points"),
    v: float = Query(..., description="vertical position, PDF points"),
    compile_id: str | None = Query(None, description="defaults to latest successful compile"),
    service: SyncTexService = Depends(get_synctex_service),
) -> InverseResult:
    try:
        result = await service.pdf_to_code(project.id, compile_id, page, h, v)
    except SyncTexNotAvailable as exc:
        raise SyncTexUnavailableError() from exc
    if result is None:
        raise SyncTexNoMatchError()
    return result
