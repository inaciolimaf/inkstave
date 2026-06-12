"""ARQ-backed compile enqueuer (spec 22). Overridden with a fake in tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from arq.connections import ArqRedis


class ArqEnqueuer:
    def __init__(self, pool: ArqRedis, queue_name: str) -> None:
        self._pool = pool
        self._queue_name = queue_name

    async def enqueue(self, compile_id: UUID) -> str | None:
        job = await self._pool.enqueue_job(
            "run_compile", str(compile_id), _queue_name=self._queue_name
        )
        return job.job_id if job is not None else None
