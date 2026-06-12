"""The ``run_compile`` ARQ job: run one compile to completion (spec 22).

The spec-21 ``CompileService.compile`` is the seam mocked in tests. The heavy
artifacts are handed to a persistence hook (spec 23), never returned via ARQ.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from inkstave.compile.limits import CancelToken
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileResult, CompileStatus
from inkstave.compile.service import CompileOptions
from inkstave.compile.stream import is_cancel_requested, publish_status
from inkstave.compile.workdir import cleanup_workdir
from inkstave.db.models.compile import Compile, CompileJobStatus, is_terminal
from inkstave.schemas.compile import CompileStatusResponse

_STATUS_MAP = {
    CompileStatus.SUCCESS: CompileJobStatus.SUCCESS,
    CompileStatus.FAILURE: CompileJobStatus.FAILURE,
    CompileStatus.TIMEOUT: CompileJobStatus.TIMEOUT,
    CompileStatus.CANCELLED: CompileJobStatus.CANCELLED,
    CompileStatus.SYSTEM_ERROR: CompileJobStatus.ERROR,
}
_CANCEL_POLL_SECONDS = 0.05


def _now() -> datetime:
    return datetime.now(UTC)


def status_payload(row: Compile) -> dict[str, Any]:
    return CompileStatusResponse.model_validate(row).model_dump(mode="json")


def _manifest(result: CompileResult) -> list[dict[str, Any]]:
    return [
        {
            "name": a.name,
            "rel_path": a.rel_path,
            "size_bytes": a.size_bytes,
            "content_type": a.content_type,
        }
        for a in result.artifacts
    ]


def _summary(row: Compile) -> dict[str, Any]:
    return {
        "compile_id": str(row.id),
        "status": row.status,
        "exit_code": row.exit_code,
        "duration_ms": row.duration_ms,
        "has_pdf": row.has_pdf,
        "artifact_count": len(row.artifact_manifest or []),
    }


async def _cancel_watcher(redis: Any, compile_id: UUID, cancel: CancelToken) -> None:
    while not cancel.is_cancelled:
        if await is_cancel_requested(redis, compile_id):
            cancel.cancel()
            return
        await asyncio.sleep(_CANCEL_POLL_SECONDS)


async def run_compile(ctx: dict[str, Any], compile_id: str) -> dict[str, Any]:
    cid = UUID(compile_id)
    settings = ctx["settings"]
    redis = ctx["redis"]
    persist_hook = ctx["persist_hook"]

    async with ctx["session_factory"]() as session:
        repo = CompileRepository(session)
        row = await repo.get_by_id(cid)
        if row is None:
            return {"compile_id": compile_id, "status": "error", "error": "compile not found"}

        # A cancel that arrived before the worker picked the job up.
        if is_terminal(CompileJobStatus(row.status)) or await is_cancel_requested(redis, cid):
            if not is_terminal(CompileJobStatus(row.status)):
                await repo.update(row, status=CompileJobStatus.CANCELLED.value, finished_at=_now())
                await session.commit()
                await publish_status(redis, cid, status_payload(row))
            return _summary(row)

        await repo.update(row, status=CompileJobStatus.RUNNING.value, started_at=_now())
        await session.commit()
        await publish_status(redis, cid, status_payload(row))

        service = ctx["make_compile_service"](session)
        cancel = CancelToken()
        watcher = asyncio.create_task(_cancel_watcher(redis, cid, cancel))
        try:
            opts = CompileOptions(
                project_id=row.project_id,
                main_file=row.main_file,
                timeout_s=settings.tectonic_compile_timeout_s,
                compile_id=cid,
                keep_workdir=True,  # the job owns cleanup, after persisting outputs
            )
            result = await service.compile(opts, cancel)
        except Exception as exc:  # a job failure, not a LaTeX failure
            await repo.update(
                row,
                status=CompileJobStatus.ERROR.value,
                error_message=str(exc)[:1000],
                finished_at=_now(),
            )
            await session.commit()
            await publish_status(redis, cid, status_payload(row))
            return _summary(row)
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

        # Persist outputs (spec 23) BEFORE the terminal event, while the workdir
        # is still alive; then the job cleans the workdir up.
        persist_error: str | None = None
        try:
            await persist_hook(session, cid, row.project_id, result)
        except Exception as exc:  # persistence failure is recorded, not crashed
            persist_error = str(exc)[:1000]
        finally:
            if result.workdir is not None:
                await cleanup_workdir(result.workdir)

        if persist_error is not None:
            await repo.update(
                row,
                status=CompileJobStatus.ERROR.value,
                error_message=f"output persistence failed: {persist_error}",
                finished_at=_now(),
            )
        else:
            job_status = _STATUS_MAP.get(result.status, CompileJobStatus.ERROR)
            await repo.update(
                row,
                status=job_status.value,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                has_pdf=result.pdf is not None,
                artifact_manifest=_manifest(result),
                log_excerpt=result.log_text[:2000] or None,
                error_message=(
                    result.log_text[:1000] if job_status is CompileJobStatus.ERROR else None
                ),
                finished_at=_now(),
            )
        await session.commit()
        await publish_status(redis, cid, status_payload(row))
        return _summary(row)


async def noop_persist_hook(
    session: Any, compile_id: UUID, project_id: UUID, result: CompileResult
) -> None:
    """No-op output-persistence seam (replaced by spec 23's OutputStore)."""
