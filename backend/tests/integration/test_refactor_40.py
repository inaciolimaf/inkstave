"""Spec-40 refactor regression tests: history correctness + storage-bloat fixes."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.collab.ydocument import YDocument
from inkstave.config import get_settings
from inkstave.db.models.history import HistoryChunk, HistoryUpdate
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.history.capture import HistoryCaptureService
from inkstave.history.jobs import compact_history
from inkstave.history.reconstruct import reconstruct_state
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from inkstave.storage.local import LocalObjectStore
from tests.collab_ws_harness import install_collab
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 10, tzinfo=UTC)
API = "/api/v1/projects"


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _settings(tmp_path: Any, **over: Any):
    return get_settings().model_copy(
        update={"history_debounce_ms": 10_000_000, "history_blob_prefix": "history/", **over}
    )


class _Editor:
    """A local Y.Doc that yields the raw update produced by each text change."""

    def __init__(self) -> None:
        self.doc = YDocument()
        self._updates: list[bytes] = []
        self.doc.observe(lambda u, _o: self._updates.append(u))

    def update(self, text: str) -> bytes:
        self.doc.replace_text(text)
        return self._updates[-1]


async def _doc(db_session: AsyncSession) -> tuple[UUID, UUID]:
    user = await UserFactory.create(db_session)
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "")
    await db_session.commit()
    return project.id, entity.id


# --- flush-on-shutdown (data-loss fix) ------------------------------------- #


async def test_flush_all_persists_buffered_updates(db_session: AsyncSession, tmp_path: Any) -> None:
    pid, doc_id = await _doc(db_session)
    svc = HistoryCaptureService(
        lambda: _SessionCtx(db_session), LocalObjectStore(tmp_path, 65536), _settings(tmp_path)
    )
    ed = _Editor()
    # Capture two updates WITHOUT flushing (high debounce → timer never fires).
    await svc.capture_update(
        project_id=pid, doc_id=doc_id, update=ed.update("one\n"), author_id=None, at=_NOW
    )
    await svc.capture_update(
        project_id=pid, doc_id=doc_id, update=ed.update("one\ntwo\n"), author_id=None, at=_NOW
    )
    # Nothing written yet.
    assert await db_session.scalar(select(func.count()).select_from(HistoryUpdate)) == 0

    await svc.flush_all()  # what the lifespan now calls on shutdown

    rows = await db_session.scalar(select(func.count()).select_from(HistoryUpdate))
    assert rows == 1  # the buffered run was flushed, not lost


# --- payload/blob XOR DB constraint ---------------------------------------- #


async def test_payload_xor_check_rejects_bad_row(db_session: AsyncSession, tmp_path: Any) -> None:
    pid, doc_id = await _doc(db_session)
    svc = HistoryCaptureService(
        lambda: _SessionCtx(db_session), LocalObjectStore(tmp_path, 65536), _settings(tmp_path)
    )
    ed = _Editor()
    await svc.capture_update(
        project_id=pid, doc_id=doc_id, update=ed.update("x\n"), author_id=None, at=_NOW
    )
    await svc.flush_doc(doc_id=doc_id, reason="manual")
    chunk_id = await db_session.scalar(select(HistoryChunk.id).where(HistoryChunk.doc_id == doc_id))

    # Both payload and blob NULL violates the new CHECK constraint.
    db_session.add(
        HistoryUpdate(
            chunk_id=chunk_id,
            project_id=pid,
            doc_id=doc_id,
            version=999,
            timestamp=_NOW,
            author_id=None,
            payload=None,
            payload_blob_key=None,
            payload_size=0,
            op_count=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


# --- compaction preserves reconstructed state (AC4) ------------------------ #


async def test_compact_preserves_reconstructed_state(
    db_session: AsyncSession, tmp_path: Any
) -> None:
    pid, doc_id = await _doc(db_session)
    # Small chunk size forces a seal; high merge bytes makes compaction merge.
    settings = _settings(
        tmp_path, history_chunk_max_updates=3, history_compact_merge_bytes=1_000_000
    )
    store = LocalObjectStore(tmp_path, 65536)
    svc = HistoryCaptureService(lambda: _SessionCtx(db_session), store, settings)

    ed = _Editor()
    text = ""
    for i in range(6):  # spans more than one chunk → at least one sealed chunk
        text += f"line {i}\n"
        await svc.capture_update(
            project_id=pid, doc_id=doc_id, update=ed.update(text), author_id=None, at=_NOW
        )
        await svc.flush_doc(doc_id=doc_id, reason="manual")

    head = await db_session.scalar(
        select(func.max(HistoryUpdate.version)).where(HistoryUpdate.doc_id == doc_id)
    )
    before = await reconstruct_state(db_session, store, doc_id, head)

    ctx = {
        "settings": settings,
        "session_factory": lambda: _SessionCtx(db_session),
        "object_store": store,
    }
    await compact_history(ctx)

    after = await reconstruct_state(db_session, store, doc_id, head)
    assert after == before  # AC4: reconstruction byte-identical after compaction


# --- restore fail-fast on duplicate label (atomicity) ---------------------- #


@pytest.fixture
async def restorable(app: Any, async_client: AsyncClient, db_session: AsyncSession, redis: Any):
    comp = install_collab(app, db_session, redis, history_debounce_ms=10_000_000)
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "")
    await db_session.commit()
    for t in ("alpha\n", "alpha\nbeta\n"):
        update = await comp.manager.apply_server_update(entity.id, t, "setup")
        await comp.history.capture_update(
            project_id=project.id, doc_id=entity.id, update=update, author_id=user.id, at=_NOW
        )
        await comp.history.flush_doc(doc_id=entity.id, reason="manual")
    return SimpleNamespace(
        comp=comp,
        pid=str(project.id),
        doc_id=str(entity.id),
        doc_uuid=entity.id,
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_restore_duplicate_label_fails_fast(
    restorable: SimpleNamespace,
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: Any,
) -> None:
    base = f"{API}/{restorable.pid}/docs/{restorable.doc_id}/history"
    # Take a label name.
    created = await async_client.post(
        f"{base}/labels", json={"version": 1, "name": "taken"}, headers=restorable.headers
    )
    assert created.status_code == 201

    published: list[Any] = []
    monkeypatch.setattr(
        restorable.comp.redis_bridge,
        "publish",
        lambda *a, **k: published.append(a),  # type: ignore[misc]
    )
    before = await db_session.scalar(
        select(func.max(HistoryUpdate.version)).where(HistoryUpdate.doc_id == restorable.doc_uuid)
    )

    r = await async_client.post(
        f"{base}/restore", json={"version": 1, "label_name": "taken"}, headers=restorable.headers
    )
    assert r.status_code == 409  # duplicate label rejected
    after = await db_session.scalar(
        select(func.max(HistoryUpdate.version)).where(HistoryUpdate.doc_id == restorable.doc_uuid)
    )
    assert after == before  # no new version created
    assert published == []  # nothing broadcast — restore was atomic
