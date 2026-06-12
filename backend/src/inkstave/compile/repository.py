"""Async data access for the ``compiles`` table (spec 22)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select

from inkstave.db.models.compile import Compile, CompileJobStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ACTIVE = (CompileJobStatus.QUEUED.value, CompileJobStatus.RUNNING.value)


class CompileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, project_id: UUID, requested_by: UUID, main_file: str) -> Compile:
        row = Compile(
            project_id=project_id,
            requested_by=requested_by,
            main_file=main_file,
            status=CompileJobStatus.QUEUED.value,
        )
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

    async def find_active_for_project(self, project_id: UUID) -> Compile | None:
        return (
            await self._session.execute(
                select(Compile)
                .where(Compile.project_id == project_id, Compile.status.in_(_ACTIVE))
                .order_by(Compile.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def count_active_for_project(self, project_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(Compile)
                .where(Compile.project_id == project_id, Compile.status.in_(_ACTIVE))
            )
            or 0
        )

    async def count_active_for_user(self, user_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(Compile)
                .where(Compile.requested_by == user_id, Compile.status.in_(_ACTIVE))
            )
            or 0
        )

    async def update(self, row: Compile, **fields: Any) -> Compile:
        for key, value in fields.items():
            setattr(row, key, value)
        await self._session.flush()
        await self._session.refresh(row)
        return row
