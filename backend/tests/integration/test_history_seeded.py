"""History of documents that had content before their first edit, and edits that change nothing.

A document opened with existing content is seeded into the CRDT by the server; editors' updates
then reference that seed. History must reconstruct those versions, must not record a version for
an update that changes nothing, and must heal a history captured before this was fixed.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.models import CrdtDocumentState, CrdtUpdate
from inkstave.modules.history.models import HistoryChunk, HistoryUpdate
from inkstave.modules.history.versions.capture import HistoryCaptureService
from tests.integration.test_history_capture import _NOW, _count, _editor, _make_doc, _service, _text

pytestmark = pytest.mark.integration

_SEED = "hello world seeded\n"


async def _seed_live(db_session: AsyncSession, doc_id: UUID) -> YDocument:
    """Seed the live CRDT store as the room does on a first open, and return an editor synced to it."""
    server = YDocument()
    server.replace_text(_SEED)
    db_session.add(
        CrdtDocumentState(
            document_id=doc_id, state=server.get_state(), state_vector=server.get_state_vector()
        )
    )
    await db_session.commit()
    editor = YDocument()
    editor.apply_update(server.get_state())
    return editor


async def _edit_live(
    db_session: AsyncSession, svc: HistoryCaptureService, editor: YDocument, ids: tuple[UUID, UUID, UUID]
) -> None:
    """One edit as the socket applies it: persisted to the live store, then captured."""
    user_id, project_id, doc_id = ids
    updates: list[bytes] = []
    editor.observe(lambda update, _origin: updates.append(update))
    editor.replace_text(editor.text.replace("world", "big world"))
    db_session.add(CrdtUpdate(document_id=doc_id, update=updates[-1]))
    await db_session.commit()
    await svc.capture_update(
        project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=user_id, at=_NOW
    )


async def test_seeded_document_versions_reconstruct(db_session: AsyncSession, tmp_path: Path) -> None:
    ids = await _make_doc(db_session)
    doc_id = ids[2]
    svc = _service(db_session, tmp_path)
    editor = await _seed_live(db_session, doc_id)

    await _edit_live(db_session, svc, editor, ids)
    await svc.flush_doc(doc_id=doc_id, reason="idle")

    assert _text(await svc.reconstruct_state(doc_id=doc_id, version=1)) == "hello big world seeded\n"


async def test_update_that_changes_nothing_records_no_version(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    user_id, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path)
    ed, updates = _editor()
    ed.replace_text("hi")
    await svc.capture_update(
        project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=None, at=_NOW
    )
    await svc.flush_doc(doc_id=doc_id, reason="manual")

    empty_step2 = YDocument().diff(ed.get_state_vector())  # what an editor sends on connect
    await svc.capture_update(
        project_id=project_id, doc_id=doc_id, update=empty_step2, author_id=user_id, at=_NOW
    )
    await svc.flush_doc(doc_id=doc_id, reason="manual")

    assert await _count(db_session, HistoryUpdate, doc_id) == 1


async def test_history_captured_on_an_empty_base_heals(db_session: AsyncSession, tmp_path: Path) -> None:
    ids = await _make_doc(db_session)
    doc_id = ids[2]
    editor = await _seed_live(db_session, doc_id)
    broken = _service(db_session, tmp_path)
    await _edit_live(db_session, broken, editor, ids)
    await broken.flush_doc(doc_id=doc_id, reason="idle")
    # Reproduce a history captured before the fix: the first chunk's base never had the seed.
    chunk = await db_session.scalar(select(HistoryChunk).where(HistoryChunk.doc_id == doc_id))
    assert chunk is not None
    chunk.base_snapshot = YDocument().get_state()
    await db_session.commit()

    svc = _service(db_session, tmp_path)  # a fresh process: the replica is rebuilt from the database
    await _edit_live(db_session, svc, editor, ids)
    await svc.flush_doc(doc_id=doc_id, reason="idle")

    assert _text(await svc.reconstruct_state(doc_id=doc_id, version=2)) == editor.text
    open_chunks = await db_session.scalars(
        select(HistoryChunk).where(HistoryChunk.doc_id == doc_id, HistoryChunk.sealed.is_(False))
    )
    assert len(list(open_chunks)) == 1
