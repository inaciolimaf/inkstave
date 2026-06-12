"""Async data access for the ``compile_outputs`` table (spec 23)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, select, text

from inkstave.db.models.compile_output import CompileOutput

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class OutputRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        compile_id: UUID,
        project_id: UUID,
        name: str,
        rel_path: str,
        kind: str,
        content_type: str,
        size_bytes: int,
        storage_key: str,
        etag: str,
    ) -> CompileOutput:
        existing = await self.get_by_name(compile_id, name)
        if existing is not None:
            existing.rel_path = rel_path
            existing.kind = kind
            existing.content_type = content_type
            existing.size_bytes = size_bytes
            existing.storage_key = storage_key
            existing.etag = etag
            await self._session.flush()
            await self._session.refresh(existing)
            return existing
        row = CompileOutput(
            compile_id=compile_id,
            project_id=project_id,
            name=name,
            rel_path=rel_path,
            kind=kind,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
            etag=etag,
        )
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
        await self._session.execute(
            delete(CompileOutput).where(CompileOutput.compile_id == compile_id)
        )
        await self._session.flush()

    async def delete_for_project(self, project_id: UUID) -> None:
        await self._session.execute(
            delete(CompileOutput).where(CompileOutput.project_id == project_id)
        )
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
        sql = text(
            """
            SELECT id FROM (
                SELECT c.id, c.created_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY c.project_id ORDER BY c.created_at DESC
                       ) AS rn
                FROM compiles c
            ) ranked
            WHERE (rn > :keep OR created_at < :cutoff)
              AND EXISTS (SELECT 1 FROM compile_outputs o WHERE o.compile_id = ranked.id)
            ORDER BY created_at ASC
            LIMIT :batch
            """
        )
        result = await self._session.execute(
            sql, {"keep": keep_per_project, "cutoff": max_age_cutoff, "batch": batch}
        )
        return [row[0] for row in result.all()]
