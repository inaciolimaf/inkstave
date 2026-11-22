"""Brokers a compile request: debounce/coalesce, concurrency caps, enqueue (spec 22)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from inkstave.core.errors import AppError
from inkstave.modules.compile.queue.stale import stale_cutoffs

if TYPE_CHECKING:
    from inkstave.core.config.settings import Settings
    from inkstave.modules.compile.models.compile import Compile
    from inkstave.modules.compile.queue.repository import CompileRepository
    from inkstave.modules.compile.queue.stale import StaleCutoffs


class CompileConcurrencyError(AppError):
    status_code = 429
    error_type = "compile_concurrency_limit"

    def __init__(self, retry_after_seconds: int = 5) -> None:
        super().__init__(
            "Too many compiles in progress for this project or user.",
            headers={"Retry-After": str(retry_after_seconds)},
        )


class CompileEnqueuer(Protocol):
    async def enqueue(self, compile_id: UUID) -> str | None:
        """Enqueue the ``run_compile`` job; return the ARQ job id (or None)."""


class CompileCoordinator:
    def __init__(
        self,
        *,
        settings: Settings,
        repo: CompileRepository,
        enqueuer: CompileEnqueuer,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._enqueuer = enqueuer

    async def request_compile(
        self, *, project_id: UUID, user_id: UUID, main_file: str, force: bool
    ) -> Compile:
        # One request at a time per project and per user, so coalescing and the caps see each other.
        await self._repo.lock_for_request(project_id, user_id)
        cutoffs = stale_cutoffs(self._settings)

        # Debounce/coalesce: return the in-flight compile unless forced.
        if not force and self._settings.compile_debounce_coalesce:
            active = await self._repo.find_active_for_project(project_id, cutoffs)
            if active is not None:
                return active

        await self._check_caps(project_id, user_id, cutoffs)

        # The job id is the compile id, so the row needs no second write once the job is queued.
        compile_id = uuid4()
        row = await self._repo.create(
            project_id=project_id,
            requested_by=user_id,
            main_file=main_file,
            compile_id=compile_id,
            job_id=str(compile_id),
        )
        # Enqueue only after the row commits: a worker must find the row it is asked to run.
        self._repo.after_commit(lambda: self._enqueue(compile_id))
        return row

    async def _check_caps(self, project_id: UUID, user_id: UUID, cutoffs: StaleCutoffs) -> None:
        """Concurrency caps (count of fresh queued + running rows)."""
        if (
            await self._repo.count_active_for_project(project_id, cutoffs)
            >= self._settings.compile_max_concurrent_per_project
        ):
            raise CompileConcurrencyError()
        per_user = await self._repo.count_active_for_user(user_id, cutoffs)
        if per_user >= self._settings.compile_max_concurrent_per_user:
            raise CompileConcurrencyError()

    async def _enqueue(self, compile_id: UUID) -> None:
        await self._enqueuer.enqueue(compile_id)
