"""Async data access for the ``project_imports`` table (spec 101).

A thin repository mirroring :class:`inkstave.compile.repository.CompileRepository`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from inkstave.db.models.project_import import ProjectImport, ProjectImportStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ProjectImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: UUID,
        requested_by: UUID,
        source_key: str,
        source_bytes: int,
        original_filename: str | None,
    ) -> ProjectImport:
        row = ProjectImport(
            project_id=project_id,
            requested_by=requested_by,
            source_key=source_key,
            source_bytes=source_bytes,
            original_filename=original_filename,
            status=ProjectImportStatus.QUEUED.value,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, project_id: UUID, import_id: UUID) -> ProjectImport | None:
        return (
            await self._session.execute(
                select(ProjectImport).where(
                    ProjectImport.id == import_id, ProjectImport.project_id == project_id
                )
            )
        ).scalar_one_or_none()

    async def get_by_id(self, import_id: UUID) -> ProjectImport | None:
        return (
            await self._session.execute(select(ProjectImport).where(ProjectImport.id == import_id))
        ).scalar_one_or_none()

    async def get_latest(self, project_id: UUID) -> ProjectImport | None:
        return (
            await self._session.execute(
                select(ProjectImport)
                .where(ProjectImport.project_id == project_id)
                .order_by(ProjectImport.created_at.desc(), ProjectImport.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def update(self, row: ProjectImport, **fields: Any) -> ProjectImport:
        for key, value in fields.items():
            setattr(row, key, value)
        await self._session.flush()
        await self._session.refresh(row)
        return row
