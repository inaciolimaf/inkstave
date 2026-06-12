"""Brokers a compile request: debounce/coalesce, concurrency caps, enqueue (spec 22)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from inkstave.errors import AppError

if TYPE_CHECKING:
    from inkstave.compile.repository import CompileRepository
    from inkstave.config import Settings
    from inkstave.db.models.compile import Compile


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
        # Debounce/coalesce: return the in-flight compile unless forced.
        if not force and self._settings.compile_debounce_coalesce:
            active = await self._repo.find_active_for_project(project_id)
            if active is not None:
                return active

        # Concurrency caps (count of queued + running).
        if (
            await self._repo.count_active_for_project(project_id)
            >= self._settings.compile_max_concurrent_per_project
        ):
            raise CompileConcurrencyError()
        if (
            await self._repo.count_active_for_user(user_id)
            >= self._settings.compile_max_concurrent_per_user
        ):
            raise CompileConcurrencyError()

        row = await self._repo.create(
            project_id=project_id, requested_by=user_id, main_file=main_file
        )
        job_id = await self._enqueuer.enqueue(row.id)
        if job_id is not None:
            await self._repo.update(row, job_id=job_id)
        return row
