"""Integration tests for history capture (spec 36): capture, snapshot, reconstruct."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.collab.ydocument import YDocument
from inkstave.config import get_settings
from inkstave.db.models.history import HistoryChunk, HistoryUpdate
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.history.capture import HistoryCaptureService
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from inkstave.storage.local import LocalObjectStore
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def _make_doc(db_session: AsyncSession) -> tuple[UUID, UUID, UUID]:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "")  # creates the documents row
    await db_session.commit()
    return user.id, project.id, entity.id


def _service(db_session: AsyncSession, tmp_path: Path, **overrides: Any) -> HistoryCaptureService:
    base = {"history_debounce_ms": 10_000_000}  # never fires; tests flush explicitly
    settings = get_settings().model_copy(update={**base, **overrides})
    store = LocalObjectStore(tmp_path, settings.storage_stream_chunk_bytes)
    return HistoryCaptureService(lambda: _SessionCtx(db_session), store, settings)


def _editor() -> tuple[YDocument, list[bytes]]:
    ed = YDocument()
    collected: list[bytes] = []
    ed.observe(lambda update, _origin: collected.append(update))
    return ed, collected


def _text(state: bytes) -> str:
    doc = YDocument()
    doc.apply_update(state)
    return doc.text


async def _count(db_session: AsyncSession, model: Any, doc_id: UUID) -> int:
    stmt = select(func.count()).select_from(model).where(model.doc_id == doc_id)
    return int(await db_session.scalar(stmt))


_NOW = datetime(2026, 6, 10, tzinfo=UTC)


# --- capture --------------------------------------------------------------- #


async def test_first_edit_creates_chunk_and_update(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    _u, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path)
    ed, updates = _editor()
    ed.replace_text("hello")

    await svc.capture_update(
        project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=_u, at=_NOW
    )
    await svc.flush_doc(doc_id=doc_id, reason="manual")

    assert await _count(db_session, HistoryChunk, doc_id) == 1  # AC1
    assert await _count(db_session, HistoryUpdate, doc_id) == 1
    chunk = await db_session.scalar(select(HistoryChunk).where(HistoryChunk.doc_id == doc_id))
    assert chunk is not None and chunk.sealed is False and chunk.base_snapshot is not None
    row = await db_session.scalar(select(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id))
    assert row is not None and row.version == 1


async def test_burst_is_coalesced(db_session: AsyncSession, tmp_path: Path) -> None:
    _u, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path)
    ed, updates = _editor()
    for t in ("a", "ab", "abc"):
        ed.replace_text(t)
        await svc.capture_update(
            project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=None, at=_NOW
        )
    await svc.flush_doc(doc_id=doc_id, reason="manual")

    assert await _count(db_session, HistoryUpdate, doc_id) == 1  # AC2: one row
    row = await db_session.scalar(select(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id))
    assert row is not None and row.op_count == 3
    state = await svc.reconstruct_state(doc_id=doc_id, version=1)
    assert _text(state) == "abc"  # merged payload replayed on base reproduces state


async def test_capture_is_non_blocking(db_session: AsyncSession, tmp_path: Path) -> None:
    _u, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path)
    ed, updates = _editor()
    ed.replace_text("x")
    await svc.capture_update(
        project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=None, at=_NOW
    )
    assert await _count(db_session, HistoryUpdate, doc_id) == 0  # AC8: nothing written yet
    await svc.flush_doc(doc_id=doc_id, reason="idle")  # AC9: room-empty/idle flush persists
    assert await _count(db_session, HistoryUpdate, doc_id) == 1


async def test_replay_is_deduped(db_session: AsyncSession, tmp_path: Path) -> None:
    _u, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path)
    ed, updates = _editor()
    ed.replace_text("hi")
    same = updates[-1]
    await svc.capture_update(
        project_id=project_id, doc_id=doc_id, update=same, author_id=None, at=_NOW
    )
    await svc.capture_update(  # identical replay
        project_id=project_id, doc_id=doc_id, update=same, author_id=None, at=_NOW
    )
    await svc.flush_doc(doc_id=doc_id, reason="manual")

    assert await _count(db_session, HistoryUpdate, doc_id) == 1  # AC6
    row = await db_session.scalar(select(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id))
    assert row is not None and row.op_count == 1 and row.version == 1


async def test_chunk_seals_at_threshold(db_session: AsyncSession, tmp_path: Path) -> None:
    _u, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path, history_chunk_max_updates=3)
    ed, updates = _editor()
    for i in range(3):
        ed.replace_text("x" * (i + 1))
        await svc.capture_update(
            project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=None, at=_NOW
        )
        await svc.flush_doc(doc_id=doc_id, reason="manual")

    chunks = list(
        (
            await db_session.execute(
                select(HistoryChunk)
                .where(HistoryChunk.doc_id == doc_id)
                .order_by(HistoryChunk.base_version)
            )
        ).scalars()
    )
    assert len(chunks) == 2  # AC3: sealed chunk + fresh open chunk
    assert chunks[0].sealed is True and chunks[0].end_version == 3
    open_chunks = [c for c in chunks if not c.sealed]
    assert len(open_chunks) == 1 and open_chunks[0].base_version == 3  # exactly one open


async def test_oversized_payload_offloads_to_blob(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    _u, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path, history_inline_max_bytes=10)
    ed, updates = _editor()
    ed.replace_text("a long string that yields an update larger than ten bytes")
    await svc.capture_update(
        project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=None, at=_NOW
    )
    await svc.flush_doc(doc_id=doc_id, reason="manual")

    row = await db_session.scalar(select(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id))
    assert row is not None
    assert row.payload is None and row.payload_blob_key is not None  # AC4
    assert row.payload_blob_key.startswith("history/")
    assert row.payload_size > 10
    # The offloaded payload is readable back from the blob store and reconstructs.
    assert _text(await svc.reconstruct_state(doc_id=doc_id, version=1)).startswith("a long string")


async def test_reconstruct_across_chunks(db_session: AsyncSession, tmp_path: Path) -> None:
    _u, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path, history_chunk_max_updates=2)
    ed, updates = _editor()
    expected: dict[int, str] = {}
    for v, t in enumerate(("a", "ab", "abc", "abcd", "abcde"), start=1):
        ed.replace_text(t)
        await svc.capture_update(
            project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=None, at=_NOW
        )
        await svc.flush_doc(doc_id=doc_id, reason="manual")
        expected[v] = t

    # Spans multiple chunks (seal every 2 updates); each captured version rebuilds (AC5).
    assert await _count(db_session, HistoryChunk, doc_id) >= 3
    for v, text in expected.items():
        assert _text(await svc.reconstruct_state(doc_id=doc_id, version=v)) == text
