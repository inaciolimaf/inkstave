"""Materialise live CRDT rooms before a worker job reads ``documents.content``.

The agent and compile jobs run in the ARQ worker and read the persisted
``documents.content`` column, which the collab ``DocumentManager`` only
materialises on a debounced timer (``collab_text_flush_debounce_ms``). Called
from a request handler — which lives in the same process as the in-memory rooms —
this first flushes the project's currently-open docs, so the worker never reads
stale text right after the user typed.

Best-effort: rooms held by another backend instance are not visible here and are
simply skipped, and any flush error is swallowed so it can never break the run
the user asked for.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.db.models.document import Document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.collab.ws.components import CollabComponents

logger = logging.getLogger(__name__)


async def flush_open_project_docs(
    collab: CollabComponents | None,
    session: AsyncSession,
    project_id: UUID,
) -> None:
    """Flush the project's currently-open CRDT rooms to ``documents.content``."""
    if collab is None:
        return
    active = collab.manager.active_document_ids()
    if not active:
        return
    rows = (
        await session.execute(
            select(Document.entity_id).where(
                Document.entity_id.in_(active),
                Document.project_id == project_id,
            )
        )
    ).scalars().all()
    for doc_id in rows:
        try:
            await collab.manager.flush(doc_id)
        except Exception:  # noqa: BLE001 — best-effort; never block the run
            logger.warning("pre-read flush failed for doc %s", doc_id, exc_info=True)
