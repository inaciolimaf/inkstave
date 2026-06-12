"""Bridge CRDT text <-> spec-13 document content (spec 28).

Keeps the canonical ``documents.content`` in sync with the live CRDT text so REST
readers and the Tectonic compiler always see current content, and seeds the CRDT
from existing content on first open. Writes go directly to the content column
(never through the CRDT), so a flush never re-emits a CRDT update.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.collab.store import SessionFactory
from inkstave.services.document_service import read_content_for_collab, set_content_from_collab

if TYPE_CHECKING:
    pass


class ContentBridge:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def load_initial_text(self, document_id: UUID) -> str:
        async with self._session_factory() as session:
            return await read_content_for_collab(session, document_id)

    async def flush_text(self, document_id: UUID, text: str) -> None:
        async with self._session_factory() as session:
            await set_content_from_collab(session, document_id, text)
            await session.commit()
