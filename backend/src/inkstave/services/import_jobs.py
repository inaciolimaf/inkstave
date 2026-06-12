"""The ``import_project_zip`` ARQ job: unpack one archive into the new project (spec 101).

Lifecycle mirrors :func:`inkstave.compile.jobs.run_compile`: bind observability
context, load the import row, re-authorize defence-in-depth, stream the staged
blob to a bounded temp file, validate + reconstruct, publish status on every
transition, and **always** clean up the staged blob + temp file. The job never
crashes — an unexpected error is recorded as ``error``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import update

from inkstave.db.models.project import Project
from inkstave.db.models.project_import import ProjectImport, ProjectImportStatus, is_terminal
from inkstave.observability.context import bind_context, clear_context
from inkstave.observability.metrics import track_job
from inkstave.schemas.project_import import ProjectImportRead
from inkstave.services.import_repository import ProjectImportRepository
from inkstave.services.import_stream import publish_status
from inkstave.services.project import ProjectNotFoundError, get_owned_project
from inkstave.services.zip_import import (
    InvalidZipError,
    ZipImportError,
    limits_from_settings,
    plan_entries,
    reconstruct_tree,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def status_payload(row: ProjectImport) -> dict[str, Any]:
    return ProjectImportRead.model_validate(row).model_dump(mode="json")


def _summary(row: ProjectImport) -> dict[str, Any]:
    return {
        "import_id": str(row.id),
        "project_id": str(row.project_id),
        "status": row.status,
        "entries_total": row.entries_total,
        "entries_imported": row.entries_imported,
        "error_type": row.error_type,
    }


async def import_project_zip(
    ctx: dict[str, Any], import_id: str, *, request_id: str | None = None
) -> dict[str, Any]:
    """Observability wrapper (spec 51): bind job context + track the job."""
    job_id = str(ctx.get("job_id") or import_id)
    rid = request_id or str(ctx.get("request_id") or uuid4().hex)
    tokens = bind_context(
        job_id=job_id, job_name="import_project_zip", request_id=rid, trace_id=rid
    )
    try:
        async with track_job("import_project_zip"):
            return await _run_import_body(ctx, import_id)
    finally:
        clear_context(tokens)


async def _run_import_body(ctx: dict[str, Any], import_id: str) -> dict[str, Any]:
    iid = UUID(import_id)
    settings = ctx["settings"]
    redis = ctx["redis"]
    store = ctx["object_store"]

    async with ctx["session_factory"]() as session:
        repo = ProjectImportRepository(session)
        row = await repo.get_by_id(iid)
        if row is None:
            return {"import_id": import_id, "status": "error", "error": "import not found"}
        if is_terminal(ProjectImportStatus(row.status)):
            return _summary(row)

        # Defence-in-depth re-authorization (spec 34): confirm the requester still
        # owns the project created up-front by the REST endpoint.
        try:
            await get_owned_project(session, row.requested_by, row.project_id)
        except ProjectNotFoundError:
            await repo.update(
                row,
                status=ProjectImportStatus.ERROR.value,
                error_type="error",
                error_message="requester no longer owns this project",
                finished_at=_now(),
            )
            await session.commit()
            await publish_status(redis, iid, status_payload(row))
            return _summary(row)

        await repo.update(row, status=ProjectImportStatus.RUNNING.value, started_at=_now())
        await session.commit()
        await publish_status(redis, iid, status_payload(row))

        workdir = Path(settings.import_workdir_root)
        tmp_path = workdir / f"{iid}.zip"
        terminal: dict[str, Any]
        try:
            await _stage_to_temp(store, row.source_key, tmp_path, settings.import_max_zip_bytes)
            terminal = await _process_archive(session, store, row, tmp_path, settings)
        except ZipImportError as exc:
            await session.rollback()
            terminal = {
                "status": ProjectImportStatus.FAILURE.value,
                "error_type": exc.error_type,
                "error_message": str(exc)[:1000],
            }
        except Exception as exc:  # the job never crashes
            await session.rollback()
            logger.exception("project import %s failed unexpectedly", iid)
            terminal = {
                "status": ProjectImportStatus.ERROR.value,
                "error_type": "error",
                "error_message": str(exc)[:1000],
            }
        finally:
            await _cleanup(store, row.source_key, tmp_path)

        # Reload (a rollback above may have expired the row) and write the result.
        row = await repo.get_by_id(iid)
        if row is None:  # pragma: no cover - defensive
            return {"import_id": import_id, "status": "error", "error": "import vanished"}
        await repo.update(row, finished_at=_now(), **terminal)
        await session.commit()
        await publish_status(redis, iid, status_payload(row))
        if row.status != ProjectImportStatus.SUCCESS.value:
            logger.info("project import %s ended status=%s", iid, row.status)
        return _summary(row)


async def _stage_to_temp(store: Any, source_key: str, tmp_path: Path, max_bytes: int) -> None:
    """Copy the staged blob to a seekable temp file, re-enforcing the size cap.

    ``zipfile`` needs a seekable file, hence the temp copy. Blocking file I/O is
    pushed off the event loop (mirroring :class:`LocalObjectStore`).
    """
    await asyncio.to_thread(tmp_path.parent.mkdir, parents=True, exist_ok=True)
    _, stream = await store.open(source_key)
    total = 0
    handle = await asyncio.to_thread(tmp_path.open, "wb")
    try:
        async for chunk in stream:
            total += len(chunk)
            if total > max_bytes:
                raise InvalidZipError("The staged archive exceeds the maximum size.")
            await asyncio.to_thread(handle.write, chunk)
    finally:
        await asyncio.to_thread(handle.close)


async def _process_archive(
    session: Any, store: Any, row: ProjectImport, tmp_path: Path, settings: Any
) -> dict[str, Any]:
    try:
        zf = zipfile.ZipFile(tmp_path)
    except zipfile.BadZipFile as exc:
        raise InvalidZipError("The uploaded file is not a valid zip archive.") from exc
    with zf:
        plan = plan_entries(zf, limits_from_settings(settings))
        outcome = await reconstruct_tree(
            session, store, row.project_id, zf, plan, settings=settings
        )

    await session.execute(
        update(Project)
        .where(Project.id == row.project_id)
        .values(root_doc_id=outcome.root_doc_entity_id)
    )

    entries_total = len(plan.entries) + plan.skipped
    entries_imported = outcome.docs_created + outcome.files_created
    status = (
        ProjectImportStatus.SUCCESS.value
        if entries_imported == entries_total
        else ProjectImportStatus.PARTIAL.value
    )
    return {
        "status": status,
        "entries_total": entries_total,
        "entries_imported": entries_imported,
        "error_type": None,
        "error_message": None,
    }


async def _cleanup(store: Any, source_key: str, tmp_path: Path) -> None:
    """Best-effort removal of the staged blob and temp file (never raises)."""
    with contextlib.suppress(Exception):
        await store.delete(source_key)
    with contextlib.suppress(FileNotFoundError):
        await asyncio.to_thread(tmp_path.unlink)
