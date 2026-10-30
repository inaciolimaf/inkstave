"""Async data access for the ``compile_outputs`` table (spec 23)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, exists, func, or_, select

from inkstave.modules.compile.models.compile import Compile
from inkstave.modules.compile.models.compile_output import CompileOutput

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class OutputRow:
    """The stored metadata for one compile artifact."""

    compile_id: UUID
    project_id: UUID
    name: str
    rel_path: str
    kind: str
    content_type: str
    size_bytes: int
    storage_key: str
    etag: str


class OutputRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, row: OutputRow) -> CompileOutput:
        """Insert the artifact's row, or refresh the existing one. Idempotent."""
        existing = await self.get_by_name(row.compile_id, row.name)
        if existing is not None:
            existing.rel_path = row.rel_path
            existing.kind = row.kind
            existing.content_type = row.content_type
            existing.size_bytes = row.size_bytes
            existing.storage_key = row.storage_key
            existing.etag = row.etag
            return await self._persist(existing)
        return await self._persist(CompileOutput(**asdict(row)), add=True)

    async def _persist(self, row: CompileOutput, *, add: bool = False) -> CompileOutput:
        if add:
            self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_for_compile(self, compile_id: UUID) -> list[CompileOutput]:
        rows = (
            await self._session.execute(
                select(CompileOutput)
                .where(CompileOutput.compile_id == compile_id)
                .order_by(CompileOutput.name)
            )
        ).scalars()
        return list(rows)

    async def get_by_name(self, compile_id: UUID, name: str) -> CompileOutput | None:
        return (
            await self._session.execute(
                select(CompileOutput).where(
                    CompileOutput.compile_id == compile_id, CompileOutput.name == name
                )
            )
        ).scalar_one_or_none()

    async def get_by_kind(self, compile_id: UUID, kind: str) -> CompileOutput | None:
        return (
            await self._session.execute(
                select(CompileOutput)
                .where(CompileOutput.compile_id == compile_id, CompileOutput.kind == kind)
                .order_by(CompileOutput.name)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def delete_for_compile(self, compile_id: UUID) -> None:
        await self._session.execute(delete(CompileOutput).where(CompileOutput.compile_id == compile_id))
        await self._session.flush()

    async def delete_for_project(self, project_id: UUID) -> None:
        await self._session.execute(delete(CompileOutput).where(CompileOutput.project_id == project_id))
        await self._session.flush()

    async def storage_keys_for_compile(self, compile_id: UUID) -> list[str]:
        rows = (
            await self._session.execute(
                select(CompileOutput.storage_key).where(CompileOutput.compile_id == compile_id)
            )
        ).scalars()
        return list(rows)

    async def storage_keys_for_project(self, project_id: UUID) -> list[str]:
        rows = (
            await self._session.execute(
                select(CompileOutput.storage_key).where(CompileOutput.project_id == project_id)
            )
        ).scalars()
        return list(rows)

    async def list_compiles_for_retention(
        self, *, keep_per_project: int, max_age_cutoff: datetime, batch: int
    ) -> list[UUID]:
        """Compile ids whose outputs should be pruned: beyond the per-project
        keep-window **or** older than the age cutoff (and still holding outputs)."""
        newest_first = func.row_number().over(
            partition_by=Compile.project_id, order_by=Compile.created_at.desc()
        )
        ranked = select(Compile.id, Compile.created_at, newest_first.label("rn")).subquery("ranked")
        has_outputs = exists().where(CompileOutput.compile_id == ranked.c.id)
        rows = await self._session.scalars(
            select(ranked.c.id)
            .where(or_(ranked.c.rn > keep_per_project, ranked.c.created_at < max_age_cutoff), has_outputs)
            .order_by(ranked.c.created_at)
            .limit(batch)
        )
        return list(rows)
