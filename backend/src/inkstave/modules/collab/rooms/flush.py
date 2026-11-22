"""Materialise the merged CRDT text into ``documents.content`` before a worker job reads it.

The agent and compile jobs run in the ARQ worker and read the persisted ``documents.content``
column. Called from a request handler, this flushes every document of the project that has CRDT
state, so the worker never reads stale text right after the user typed. The candidates come from
the database, so a room open on another replica is covered too: its acknowledged edits are in the
stored state (ADR 0123). The flush writes the merged state, so it never writes older text.

Best-effort: any flush error is swallowed so it can never break the run the user asked for.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import false, or_, select

from inkstave.modules.collab.models import CrdtDocumentState, CrdtUpdate
from inkstave.modules.projects import Document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.modules.collab.ws.components import CollabComponents

logger = logging.getLogger(__name__)


async def flush_open_project_docs(
    collab: CollabComponents | None,
    session: AsyncSession,
    project_id: UUID,
) -> None:
    """Flush the merged CRDT text of the project's documents to ``documents.content``."""
    if collab is None:
        return
    doc_ids = await _documents_with_crdt_state(session, project_id, collab.manager.active_document_ids())
    for doc_id in doc_ids:
        try:
            await collab.manager.flush(doc_id)
        except Exception:  # broad on purpose: best-effort flush must never block the run
            logger.warning("pre-read flush failed for doc %s", doc_id, exc_info=True)


async def _documents_with_crdt_state(
    session: AsyncSession, project_id: UUID, active: set[UUID]
) -> list[UUID]:
    """Documents of the project with a stored CRDT snapshot or log rows, plus the ones open here."""
    stored = or_(
        Document.entity_id.in_(select(CrdtDocumentState.document_id)),
        Document.entity_id.in_(select(CrdtUpdate.document_id)),
        Document.entity_id.in_(active) if active else false(),
    )
    rows = await session.execute(select(Document.entity_id).where(Document.project_id == project_id, stored))
    return list(rows.scalars().all())
