"""The ``run_compile`` ARQ job: run one compile to completion (spec 22).

The spec-21 ``CompileService.compile`` is the seam mocked in tests. The heavy
artifacts are handed to a persistence hook (spec 23), never returned via ARQ.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from inkstave.authorization.capabilities import Capability, capabilities_for
from inkstave.authorization.service import role_for
from inkstave.compile.limits import CancelToken
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileResult, CompileStatus
from inkstave.compile.service import CompileOptions
from inkstave.compile.stream import is_cancel_requested, publish_status
from inkstave.compile.workdir import cleanup_workdir
from inkstave.db.models.compile import Compile, CompileJobStatus, is_terminal
from inkstave.observability.context import bind_context, clear_context
from inkstave.observability.metrics import observe_compile, track_job
from inkstave.schemas.compile import CompileStatusResponse

logger = logging.getLogger(__name__)

# CompileJobStatus value → the bounded `status` label on the compile metrics.
_METRIC_STATUS = {"success": "success", "failure": "failure", "timeout": "timeout"}

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
    # Cancellation mechanism (spec 22 §5.4.2, per ADR): the worker intentionally
    # POLLS the cancel *flag* (a Redis key `stream.request_cancel` sets) rather
    # than subscribing to the `compile:cancel:{compile_id}` pub/sub channel.
    # `stream.request_cancel` sets the flag alongside the pub/sub publish, so
    # flag-polling is functionally equivalent and strictly simpler/lower-risk in
    # the worker (no subscription lifecycle to manage). Pub/sub subscription is
    # deliberately NOT used here.
    while not cancel.is_cancelled:
        if await is_cancel_requested(redis, compile_id):
            cancel.cancel()
            return
        await asyncio.sleep(_CANCEL_POLL_SECONDS)


async def run_compile(
    ctx: dict[str, Any], compile_id: str, *, request_id: str | None = None
) -> dict[str, Any]:
    """Observability wrapper (spec 51): bind job context + record duration/compile metrics.

    ``request_id`` chains the enqueuing request's correlation id into the job's logs.
    """
    job_id = str(ctx.get("job_id") or compile_id)
    rid = request_id or str(ctx.get("request_id") or uuid4().hex)
    tokens = bind_context(job_id=job_id, job_name="run_compile", request_id=rid, trace_id=rid)
    start = perf_counter()
    try:
        async with track_job("run_compile"):
            summary = await _run_compile_body(ctx, compile_id)
        status = _METRIC_STATUS.get(str(summary.get("status", "")), "failure")
        observe_compile("tectonic", status, perf_counter() - start)
        return summary
    finally:
        clear_context(tokens)


@dataclass(slots=True)
class _Job:
    """One compile row plus the writers every job step needs."""

    session: Any
    repo: CompileRepository
    redis: Any
    cid: UUID
    row: Compile

    async def announce(self, **fields: Any) -> None:
        """Apply a row transition, commit it, and publish the status event."""
        await self.repo.update(self.row, **fields)
        await self.session.commit()
        await publish_status(self.redis, self.cid, status_payload(self.row))

    async def finish(self, **fields: Any) -> dict[str, Any]:
        """`announce` a terminal transition and return the job summary."""
        await self.announce(**fields)
        return _summary(self.row)


async def _fail(job: _Job, message: str) -> dict[str, Any]:
    """Settle the row as ERROR with `message` (truncated to the column width)."""
    return await job.finish(
        status=CompileJobStatus.ERROR.value, error_message=message[:1000], finished_at=_now()
    )


async def _settle_if_cancelled(job: _Job) -> dict[str, Any] | None:
    """Settle a compile that is already terminal, or was cancelled before pickup."""
    already_terminal = is_terminal(CompileJobStatus(job.row.status))
    if already_terminal:
        return _summary(job.row)
    if not await is_cancel_requested(job.redis, job.cid):
        return None
    return await job.finish(status=CompileJobStatus.CANCELLED.value, finished_at=_now())


async def _settle_if_unauthorized(job: _Job) -> dict[str, Any] | None:
    """Defense-in-depth re-authorization (spec 34 §5.2).

    The compile ARQ job entry re-verifies COMPILE + active membership for the
    requesting user, even though the REST trigger already authorized before
    enqueue. It reuses the same authorization seam (`role_for` + the capability
    matrix) the REST endpoint uses. If the requester lost membership/capability
    between enqueue and pickup, fail the compile gracefully instead of running it.
    """
    role = await role_for(job.session, job.row.requested_by, job.row.project_id)
    if Capability.COMPILE in capabilities_for(role):
        return None
    return await _fail(job, "requester no longer authorized to compile this project")


async def _compile_with_cancel(job: _Job, service: Any, settings: Any) -> CompileResult:
    """Run the compile with a cancel watcher attached for its whole lifetime."""
    cancel = CancelToken()
    watcher = asyncio.create_task(_cancel_watcher(job.redis, job.cid, cancel))
    try:
        opts = CompileOptions(
            project_id=job.row.project_id,
            main_file=job.row.main_file,
            timeout_s=settings.tectonic_compile_timeout_s,
            compile_id=job.cid,
            keep_workdir=True,  # the job owns cleanup, after persisting outputs
        )
        return await service.compile(opts, cancel)
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher


async def _persist_outputs(job: _Job, persist_hook: Any, result: CompileResult) -> str | None:
    """Persist outputs (spec 23) BEFORE the terminal event, while the workdir is
    still alive; then clean the workdir up. Returns the failure message, if any."""
    try:
        await persist_hook(job.session, job.cid, job.row.project_id, result)
    except Exception as exc:  # persistence failure is recorded, not crashed
        return str(exc)[:1000]
    finally:
        if result.workdir is not None:
            await cleanup_workdir(result.workdir)
    return None


def _outcome_fields(result: CompileResult, persist_error: str | None) -> dict[str, Any]:
    """The terminal row fields for a compile that actually ran."""
    if persist_error is not None:
        return {
            "status": CompileJobStatus.ERROR.value,
            "error_message": f"output persistence failed: {persist_error}",
            "finished_at": _now(),
        }
    job_status = _STATUS_MAP.get(result.status, CompileJobStatus.ERROR)
    return {
        "status": job_status.value,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "has_pdf": result.pdf is not None,
        "artifact_manifest": _manifest(result),
        # Tail, not head (spec 22 §5.1): for LaTeX the meaningful errors live at the
        # END of the log, so keep the last 2000 chars.
        "log_excerpt": result.log_text[-2000:] or None,
        "error_message": (result.log_text[:1000] if job_status is CompileJobStatus.ERROR else None),
        "finished_at": _now(),
    }


def _log_non_success(job: _Job) -> None:
    """Surface the reason in the worker log (the arq result summary truncates it).

    The fullest detail lives in error_message / the log tail.
    """
    if job.row.status == CompileJobStatus.SUCCESS.value:
        return
    logger.warning(
        "compile %s ended status=%s: %s",
        job.cid,
        job.row.status,
        (job.row.error_message or job.row.log_excerpt or "")[:500],
    )


async def _compile_once(
    ctx: dict[str, Any], session: Any, cid: UUID, compile_id: str
) -> dict[str, Any]:
    """The compile job proper: settle-or-run one row, inside the caller's session."""
    repo = CompileRepository(session)
    row = await repo.get_by_id(cid)
    if row is None:
        return {"compile_id": compile_id, "status": "error", "error": "compile not found"}

    job = _Job(session, repo, ctx["redis"], cid, row)
    settled = await _settle_if_cancelled(job)
    if settled is None:
        settled = await _settle_if_unauthorized(job)
    if settled is not None:
        return settled

    await job.announce(status=CompileJobStatus.RUNNING.value, started_at=_now())
    service = ctx["make_compile_service"](session)
    try:
        result = await _compile_with_cancel(job, service, ctx["settings"])
    except Exception as exc:  # a job failure, not a LaTeX failure
        return await _fail(job, str(exc))

    persist_error = await _persist_outputs(job, ctx["persist_hook"], result)
    summary = await job.finish(**_outcome_fields(result, persist_error))
    _log_non_success(job)
    return summary


async def _run_compile_body(ctx: dict[str, Any], compile_id: str) -> dict[str, Any]:
    # The job owns workdir cleanup (spec 23): the service runs with
    # keep_workdir=True so outputs can be persisted, then the job removes the dir.
    # This top-level finally is the backstop that guarantees no workdir is ever
    # orphaned under COMPILE_WORKDIR_ROOT on ANY exit path — service exception,
    # persistence failure, or early return included. cleanup_workdir never raises.
    workdir_path = Path(ctx["settings"].compile_workdir_root) / compile_id
    async with ctx["session_factory"]() as session:
        try:
            return await _compile_once(ctx, session, UUID(compile_id), compile_id)
        finally:
            # Backstop: remove the workdir on every path (idempotent; never raises).
            await cleanup_workdir(workdir_path)


async def noop_persist_hook(
    session: Any, compile_id: UUID, project_id: UUID, result: CompileResult
) -> None:
    """No-op output-persistence seam (replaced by spec 23's OutputStore)."""
