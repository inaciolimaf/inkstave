"""Compile problems endpoint: parsed LaTeX-log diagnostics (spec 27)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, status

from inkstave.authorization.capabilities import Capability
from inkstave.authorization.dependencies import require_capability
from inkstave.compile.output_repository import OutputRepository
from inkstave.compile.outputs import OutputStore
from inkstave.compile.repository import CompileRepository
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_object_store, get_settings_dep
from inkstave.errors import ErrorEnvelope, NotFoundError
from inkstave.logparse.models import CompileProblems
from inkstave.logparse.service import LogNotAvailable, LogProblemsService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.db.models.project import Project
    from inkstave.storage.base import ObjectStore

router = APIRouter(prefix="/projects/{project_id}/compiles", tags=["problems"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}


class LogUnavailableError(NotFoundError):
    error_type = "log_unavailable"

    def __init__(self) -> None:
        super().__init__("log_unavailable")


# Read-only compile-problems access: any active member (spec 34). Non-member -> 404.
owned_project = require_capability(Capability.PROJECT_READ)


def get_log_problems_service(
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
) -> LogProblemsService:
    output_store = OutputStore(storage=store, repo=OutputRepository(session), settings=settings)
    return LogProblemsService(
        repo=CompileRepository(session), output_store=output_store, settings=settings
    )


@router.get(
    "/{compile_id}/problems",
    response_model=CompileProblems,
    summary="Parsed LaTeX-log problems for a compile ('latest' allowed)",
    responses=_ERRORS,
)
async def get_problems(
    compile_id: str,
    project: Project = Depends(owned_project),
    service: LogProblemsService = Depends(get_log_problems_service),
) -> CompileProblems:
    try:
        return await service.problems_for(project.id, compile_id)
    except LogNotAvailable as exc:
        raise LogUnavailableError() from exc
