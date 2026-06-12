"""Concrete document/file sources backed by specs 13 & 14 (spec 21).

These adapters keep the compile module decoupled: the service depends only on the
``DocumentSource`` / ``FileSource`` protocols, while these read the real tables
and compute each entity's relative path from the tree.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.db.models.document import Document
from inkstave.db.models.file import File
from inkstave.db.models.tree_entity import TreeEntity
from inkstave.services.tree_service import compute_path

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.storage.base import ObjectStore


async def _entities_by_id(session: AsyncSession, project_id: UUID) -> dict[UUID, TreeEntity]:
    rows = (
        await session.execute(select(TreeEntity).where(TreeEntity.project_id == project_id))
    ).scalars()
    return {e.id: e for e in rows}


class DbDocumentSource:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def iter_documents(self, project_id: UUID) -> AsyncIterator[tuple[str, str]]:
        by_id = await _entities_by_id(self._session, project_id)
        docs = (
            await self._session.execute(select(Document).where(Document.project_id == project_id))
        ).scalars()
        for doc in docs:
            entity = by_id.get(doc.entity_id)
            if entity is not None:
                yield compute_path(entity, by_id), doc.content


class StorageFileSource:
    def __init__(self, session: AsyncSession, store: ObjectStore) -> None:
        self._session = session
        self._store = store

    async def iter_files(self, project_id: UUID) -> AsyncIterator[tuple[str, AsyncIterator[bytes]]]:
        by_id = await _entities_by_id(self._session, project_id)
        files = (
            await self._session.execute(select(File).where(File.project_id == project_id))
        ).scalars()
        for file_row in files:
            entity = by_id.get(file_row.entity_id)
            if entity is None:
                continue
            _, stream = await self._store.open(file_row.storage_key)
            yield compute_path(entity, by_id), stream
