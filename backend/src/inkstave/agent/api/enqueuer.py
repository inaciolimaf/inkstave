"""ARQ-backed enqueuer for agent turns (spec 44). Faked in tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.observability.context import request_id_var

if TYPE_CHECKING:
    from arq.connections import ArqRedis


class AgentEnqueuer:
    def __init__(self, pool: ArqRedis, queue_name: str) -> None:
        self._pool = pool
        self._queue_name = queue_name

    async def enqueue(self, *, session_id: UUID, run_id: UUID, user_message: str) -> str | None:
        # Chain the enqueuing request's correlation id into the job (spec 51/55 §5.4),
        # mirroring the compile enqueuer so agent logs trace back to the HTTP request.
        job = await self._pool.enqueue_job(
            "run_agent_turn",
            session_id=str(session_id),
            run_id=str(run_id),
            user_message=user_message,
            request_id=request_id_var.get(),
            _queue_name=self._queue_name,
        )
        return job.job_id if job is not None else None
