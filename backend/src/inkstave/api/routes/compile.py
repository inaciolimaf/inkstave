"""Async compile API: enqueue, status, latest, SSE events, cancel (spec 22)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from inkstave.api.routes.compile_helpers import (
    _ERRORS,
    CompileNotFoundError,
    _pdf_headers,
    _require_compile,
    _sse_user,
    get_output_store,
)
from inkstave.auth.dependencies import get_current_user
from inkstave.authorization.capabilities import Capability
from inkstave.authorization.dependencies import require_capability
from inkstave.authorization.service import role_for
from inkstave.collab.flush import flush_open_project_docs
from inkstave.compile.coordinator import CompileCoordinator, CompileEnqueuer
from inkstave.compile.jobs import status_payload
from inkstave.compile.outputs import ByteRange, OutputStore, RangeResult, parse_range
from inkstave.compile.repository import CompileRepository
from inkstave.compile.stream import publish_status, request_cancel, sse_stream
from inkstave.db.models.compile import CompileJobStatus, is_terminal
from inkstave.db.session import get_db_session
from inkstave.dependencies import (
    get_compile_enqueuer,
    get_redis,
    get_settings_dep,
)
from inkstave.schemas.compile import CompileRequest, CompileStatusResponse, OutputSummary
from inkstave.security.rate_limit import rate_limit_named
from inkstave.services.project import ProjectNotFoundError

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.db.models.compile import Compile
    from inkstave.db.models.project import Project
    from inkstave.db.models.user import User

router = APIRouter(prefix="/projects/{project_id}/compile", tags=["compile"])


# Compile is allowed for every active member (viewers included by default, spec 34).
owned_project = require_capability(Capability.COMPILE)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CompileStatusResponse,
    summary="Enqueue a compile",
    responses=_ERRORS,
    dependencies=[Depends(rate_limit_named("compile"))],
)
async def enqueue_compile(
    data: CompileRequest,
    request: Request,
    project: Project = Depends(owned_project),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    enqueuer: CompileEnqueuer = Depends(get_compile_enqueuer),
) -> CompileStatusResponse:
    # Materialise open CRDT rooms so the worker compiles the current text, not the
    # debounced-stale documents.content column (spec 28).
    await flush_open_project_docs(getattr(request.app.state, "collab", None), session, project.id)
    coordinator = CompileCoordinator(
        settings=settings, repo=CompileRepository(session), enqueuer=enqueuer
    )
    row = await coordinator.request_compile(
        project_id=project.id,
        user_id=user.id,
        main_file=data.main_file or "main.tex",
        force=data.force,
    )
    return CompileStatusResponse.model_validate(row)


@router.get(
    "/latest",
    response_model=CompileStatusResponse,
    summary="Get the most recent compile",
    responses=_ERRORS,
)
async def get_latest_compile(
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
) -> CompileStatusResponse:
    row = await CompileRepository(session).get_latest(project.id)
    if row is None:
        raise CompileNotFoundError()
    return CompileStatusResponse.model_validate(row)


@router.get(
    "/{compile_id}",
    response_model=CompileStatusResponse,
    summary="Get a compile's status",
    responses=_ERRORS,
)
async def get_compile(
    compile_id: UUID,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
) -> CompileStatusResponse:
    row = await CompileRepository(session).get(project.id, compile_id)
    if row is None:
        raise CompileNotFoundError()
    return CompileStatusResponse.model_validate(row)


@router.post(
    "/{compile_id}/cancel",
    response_model=CompileStatusResponse,
    summary="Request cancellation of a compile",
    responses=_ERRORS,
)
async def cancel_compile(
    compile_id: UUID,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> CompileStatusResponse:
    repo = CompileRepository(session)
    row = await repo.get(project.id, compile_id)
    if row is None:
        raise CompileNotFoundError()

    current = CompileJobStatus(row.status)
    if is_terminal(current):
        return CompileStatusResponse.model_validate(row)  # idempotent

    # Signal a running worker, and abort a still-queued compile directly.
    await request_cancel(redis, compile_id, settings.compile_cancel_flag_ttl_s)
    if current is CompileJobStatus.QUEUED:
        await repo.update(
            row, status=CompileJobStatus.CANCELLED.value, finished_at=datetime.now(UTC)
        )
        await publish_status(redis, compile_id, status_payload(row))
    return CompileStatusResponse.model_validate(row)


# --------------------------------------------------------------------------- #
# Output retrieval (spec 23)
# --------------------------------------------------------------------------- #


@router.get(
    "/{compile_id}/outputs",
    response_model=list[OutputSummary],
    summary="List a compile's stored outputs",
    responses=_ERRORS,
)
async def list_outputs(
    compile_id: UUID,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
    outputs: OutputStore = Depends(get_output_store),
) -> list[OutputSummary]:
    await _require_compile(session, project.id, compile_id)
    rows = await outputs.list_outputs(compile_id)
    return [OutputSummary.model_validate(r) for r in rows]


@router.get(
    "/{compile_id}/output.pdf",
    summary="Stream the compiled PDF (range-capable)",
    responses=_ERRORS,
)
async def get_output_pdf(
    compile_id: UUID,
    request: Request,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
    outputs: OutputStore = Depends(get_output_store),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    await _require_compile(session, project.id, compile_id)
    obj = await outputs.open_pdf(compile_id)
    if obj is None:
        raise CompileNotFoundError()

    headers = _pdf_headers(obj, settings)
    if request.headers.get("if-none-match") == obj.etag:
        return Response(status_code=304, headers=headers)

    spec = parse_range(request.headers.get("range"), obj.size)
    if spec is RangeResult.UNSATISFIABLE:
        return Response(
            status_code=416, headers={**headers, "Content-Range": f"bytes */{obj.size}"}
        )
    if spec is RangeResult.FULL:
        return StreamingResponse(
            obj.stream(),
            status_code=200,
            media_type="application/pdf",
            headers={**headers, "Content-Length": str(obj.size)},
        )
    assert isinstance(spec, ByteRange)
    return StreamingResponse(
        obj.read_range(spec.start, spec.end),
        status_code=206,
        media_type="application/pdf",
        headers={
            **headers,
            "Content-Range": f"bytes {spec.start}-{spec.end}/{obj.size}",
            "Content-Length": str(spec.length),
        },
    )


@router.get(
    "/{compile_id}/output.log",
    summary="Stream the compile log",
    responses=_ERRORS,
)
async def get_output_log(
    compile_id: UUID,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
    outputs: OutputStore = Depends(get_output_store),
) -> StreamingResponse:
    await _require_compile(session, project.id, compile_id)
    obj = await outputs.open_log(compile_id)
    if obj is None:
        raise CompileNotFoundError()
    return StreamingResponse(
        obj.stream(),
        media_type="text/plain; charset=utf-8",
        headers={"ETag": obj.etag, "Content-Length": str(obj.size)},
    )


@router.get(
    "/{compile_id}/events",
    summary="Live compile status (Server-Sent Events)",
    responses=_ERRORS,
)
async def compile_events(
    compile_id: UUID,
    project_id: UUID,
    user: User = Depends(_sse_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    # SSE uses a query-param token (EventSource can't set headers), so authorize
    # inline: any active member may read compile events (COMPILE capability).
    if await role_for(session, user.id, project_id) is None:
        raise ProjectNotFoundError()  # 404 — non-member / missing project
    repo = CompileRepository(session)
    if await repo.get(project_id, compile_id) is None:
        raise CompileNotFoundError()

    async def snapshot() -> dict[str, Any] | None:
        row: Compile | None = await repo.get(project_id, compile_id)
        return status_payload(row) if row is not None else None

    return StreamingResponse(
        sse_stream(redis, compile_id, snapshot, settings.compile_sse_keepalive_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
