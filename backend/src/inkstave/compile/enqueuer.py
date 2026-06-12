"""ARQ-backed compile enqueuer (spec 22). Overridden with a fake in tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.observability.context import request_id_var

if TYPE_CHECKING:
    from arq.connections import ArqRedis


class ArqEnqueuer:
    def __init__(self, pool: ArqRedis, queue_name: str) -> None:
        self._pool = pool
        self._queue_name = queue_name

    async def enqueue(self, compile_id: UUID) -> str | None:
        # Chain the enqueuing request's correlation id into the job (spec 51 §5.4).
        job = await self._pool.enqueue_job(
            "run_compile",
            str(compile_id),
            request_id=request_id_var.get(),
            _queue_name=self._queue_name,
        )
        return job.job_id if job is not None else None
