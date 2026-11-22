"""Bridge CRDT text -> spec-13 document content (spec 28).

Keeps the canonical ``documents.content`` in sync with the merged CRDT text so REST
readers and the Tectonic compiler always see current content. Writes go directly to the
content column (never through the CRDT), so a flush never re-emits a CRDT update. The
seed of an empty CRDT from existing content lives in ``CrdtStore.load``, under its lock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.modules.collab.rooms.store import SessionFactory
from inkstave.modules.projects import set_content_from_collab

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ContentBridge:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def write_text(self, session: AsyncSession, document_id: UUID, text: str) -> None:
        """Write ``text`` in the caller's transaction (the store holds the lock around it)."""
        await set_content_from_collab(session, document_id, text)

    async def flush_text(self, document_id: UUID, text: str) -> None:
        async with self._session_factory() as session:
            await self.write_text(session, document_id, text)
            await session.commit()
