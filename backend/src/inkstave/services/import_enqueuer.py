"""ARQ-backed enqueuer for project-import jobs (spec 101). Faked in tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.observability.context import request_id_var

if TYPE_CHECKING:
    from arq.connections import ArqRedis


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
