"""Compile problems endpoint: parsed LaTeX-log diagnostics (spec 27)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, status

from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.deps import get_settings_dep
from inkstave.core.errors import ErrorEnvelope, NotFoundError
from inkstave.infra.deps import get_object_store
from inkstave.modules.compile.logparse.models import CompileProblems
from inkstave.modules.compile.logparse.service import LogNotAvailableError, LogProblemsService
from inkstave.modules.compile.outputs.repository import OutputRepository
from inkstave.modules.compile.outputs.store import OutputStore
from inkstave.modules.compile.queue.repository import CompileRepository
from inkstave.modules.projects import Capability, require_capability

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings
    from inkstave.infra.storage.base import ObjectStore
    from inkstave.modules.projects import Project

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
    session: AsyncSession = UNIT_OF_WORK,
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
) -> LogProblemsService:
    output_store = OutputStore(storage=store, repo=OutputRepository(session), settings=settings)
    return LogProblemsService(repo=CompileRepository(session), output_store=output_store, settings=settings)


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
    except LogNotAvailableError as exc:
        raise LogUnavailableError() from exc
