"""Async data access for the ``compiles`` table (spec 22)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select, update

from inkstave.core.db.session import after_commit as register_after_commit
from inkstave.modules.compile.models.compile import Compile, CompileJobStatus
from inkstave.modules.compile.queue.stale import StaleCutoffs, fresh_active_clause, stale_clause

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncSession

_ACTIVE = (CompileJobStatus.QUEUED.value, CompileJobStatus.RUNNING.value)


def _active(cutoffs: StaleCutoffs | None) -> ColumnElement[bool]:
    """The active filter: every active row, or only the fresh ones when ``cutoffs`` is given."""
    if cutoffs is None:
        return Compile.status.in_(_ACTIVE)
    return fresh_active_clause(cutoffs)


class CompileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: UUID,
        requested_by: UUID,
        main_file: str,
        compile_id: UUID | None = None,
        job_id: str | None = None,
    ) -> Compile:
        row = Compile(
            project_id=project_id,
            requested_by=requested_by,
            main_file=main_file,
            status=CompileJobStatus.QUEUED.value,
            job_id=job_id,
        )
        if compile_id is not None:
            row.id = compile_id  # the caller names the id it enqueues before the row commits
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, project_id: UUID, compile_id: UUID) -> Compile | None:
        return (
            await self._session.execute(
                select(Compile).where(Compile.id == compile_id, Compile.project_id == project_id)
            )
        ).scalar_one_or_none()

    async def get_by_id(self, compile_id: UUID) -> Compile | None:
        return (
            await self._session.execute(select(Compile).where(Compile.id == compile_id))
        ).scalar_one_or_none()

    async def get_latest(self, project_id: UUID) -> Compile | None:
        return (
            await self._session.execute(
                select(Compile)
                .where(Compile.project_id == project_id)
                .order_by(Compile.created_at.desc(), Compile.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get_latest_successful(self, project_id: UUID) -> Compile | None:
        return (
            await self._session.execute(
                select(Compile)
                .where(
                    Compile.project_id == project_id,
                    Compile.status == CompileJobStatus.SUCCESS.value,
                )
                .order_by(Compile.created_at.desc(), Compile.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def find_active_for_project(
        self, project_id: UUID, cutoffs: StaleCutoffs | None = None
    ) -> Compile | None:
        """The newest active compile. With ``cutoffs``, stale rows are ignored (see ``queue.stale``)."""
        statement = select(Compile).where(Compile.project_id == project_id, _active(cutoffs))
        return (
            await self._session.execute(statement.order_by(Compile.created_at.desc()).limit(1))
        ).scalar_one_or_none()

    async def count_active_for_project(self, project_id: UUID, cutoffs: StaleCutoffs | None = None) -> int:
        return await self._count(Compile.project_id == project_id, _active(cutoffs))

    async def count_active_for_user(self, user_id: UUID, cutoffs: StaleCutoffs | None = None) -> int:
        return await self._count(Compile.requested_by == user_id, _active(cutoffs))

    async def _count(self, *where: ColumnElement[bool]) -> int:
        return int(await self._session.scalar(select(func.count()).select_from(Compile).where(*where)) or 0)

    async def lock_for_request(self, project_id: UUID, user_id: UUID) -> None:
        """Serialise compile requests for this project and this user until the transaction ends.

        The caps are a count followed by an insert, so two requests could both count below the cap.
        A transaction-level advisory lock (project first, then user, always in that order) makes the
        count and the insert one step for everyone who asks for the same project or user.
        """
        for key in (f"compile:project:{project_id}", f"compile:user:{user_id}"):
            await self._session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))

    def after_commit(self, action: Callable[[], Awaitable[object]]) -> None:
        """Run ``action`` after the request's transaction commits, such as the enqueue of its job."""
        register_after_commit(self._session, action)

    async def reap_stale(self, cutoffs: StaleCutoffs, *, now: datetime, message: str) -> list[Compile]:
        """Settle every stale active row as ``timeout`` in one statement, and return the rows."""
        statement = (
            update(Compile)
            .where(stale_clause(cutoffs))
            .values(status=CompileJobStatus.TIMEOUT.value, finished_at=now, error_message=message)
            .returning(Compile)
            .execution_options(synchronize_session=False)
        )
        return list((await self._session.scalars(statement)).all())

    async def update(self, row: Compile, **fields: Any) -> Compile:
        for key, value in fields.items():
            setattr(row, key, value)
        await self._session.flush()
        await self._session.refresh(row)
        return row
