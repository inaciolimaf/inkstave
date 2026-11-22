"""ARQ-backed enqueuer for project-import jobs (spec 101). Faked in tests."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.core.observability.context import request_id_var
from inkstave.infra.storage.after_commit import schedule_delete_after_commit
from inkstave.modules.projects.models.project_import import ProjectImportStatus
from inkstave.modules.projects.transfer.repository import ProjectImportRepository

if TYPE_CHECKING:
    from arq.connections import ArqRedis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from inkstave.infra.storage.base import ObjectStore

logger = logging.getLogger(__name__)


class ImportEnqueuer:
    def __init__(self, pool: ArqRedis, queue_name: str) -> None:
        self._pool = pool
        self._queue_name = queue_name

    async def enqueue(self, import_id: UUID) -> str | None:
        # Chain the enqueuing request's correlation id into the job (spec 51 §5.4),
        # mirroring the compile enqueuer so import logs trace back to the request.
        job = await self._pool.enqueue_job(
            "import_project_zip",
            str(import_id),
            request_id=request_id_var.get(),
            _queue_name=self._queue_name,
        )
        return job.job_id if job is not None else None


@dataclass(frozen=True)
class ImportServices:
    """What an import request needs beyond the session: the blob store, the job enqueuer and sessions."""

    store: ObjectStore
    enqueuer: ImportEnqueuer
    sessions: async_sessionmaker[AsyncSession]


async def dispatch_import(services: ImportServices, import_id: UUID, source_key: str) -> None:
    """Enqueue an import's job, from a background task that runs after the request's commit.

    The job reads the ``project_imports`` row, so the row must be committed before the job can run.
    If the enqueue fails, the import ends ``error`` (the empty project stays, as for any failed import)
    and the staged archive is removed, since no job will run to remove it.
    """
    store = services.store
    async with services.sessions() as session:
        repo = ProjectImportRepository(session)
        row = await repo.get_by_id(import_id)
        if row is None:
            return
        try:
            job_id = await services.enqueuer.enqueue(import_id)
        except Exception:
            logger.exception("import_enqueue_failed: import_id=%s", import_id)
            await repo.update(
                row,
                status=ProjectImportStatus.ERROR.value,
                error_type="enqueue_failed",
                error_message="The import could not be queued. Try again.",
                finished_at=datetime.now(UTC),
            )
            schedule_delete_after_commit(session, store, [source_key])
            await session.commit()
            return
        if job_id is not None:
            await repo.update(row, job_id=job_id)
            await session.commit()
