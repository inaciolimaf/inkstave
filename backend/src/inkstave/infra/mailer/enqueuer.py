"""ARQ-backed email enqueuer (spec 39). Overridden with a capturing fake in tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arq.connections import ArqRedis


class EmailEnqueuer:
    def __init__(self, pool: ArqRedis, queue_name: str) -> None:
        self._pool = pool
        self._queue_name = queue_name

    async def enqueue_email(self, *, template: str, to: str, context: dict[str, Any]) -> str | None:
        job = await self._pool.enqueue_job(
            "send_email_job",
            template=template,
            to=to,
            context=context,
            _queue_name=self._queue_name,
        )
        return job.job_id if job is not None else None
