"""Deleting a document removes its offloaded history blobs, after the commit (spec 36 hardening)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.infra.storage.local import LocalObjectStore
from inkstave.modules.history.blobs import purge_blobs_after_commit, purge_blobs_for_deleted
from inkstave.modules.history.models import HistoryChunk, HistoryUpdate
from inkstave.modules.projects.tree import service as tree_service
from inkstave.modules.projects.tree.service import on_entities_deleted
from tests.integration.test_history_capture import _NOW, _editor, _make_doc, _service

pytestmark = pytest.mark.integration


async def _blob_keys(db_session: AsyncSession, doc_id: UUID) -> list[str]:
    chunk_keys = await db_session.scalars(
        select(HistoryChunk.base_snapshot_blob_key).where(
            HistoryChunk.doc_id == doc_id, HistoryChunk.base_snapshot_blob_key.is_not(None)
        )
    )
    update_keys = await db_session.scalars(
        select(HistoryUpdate.payload_blob_key).where(
            HistoryUpdate.doc_id == doc_id, HistoryUpdate.payload_blob_key.is_not(None)
        )
    )
    return [*chunk_keys, *update_keys]


async def _wait_until_gone(store: LocalObjectStore, keys: list[str]) -> None:
    for _ in range(200):  # about two seconds
        if not any([await store.exists(key) for key in keys]):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the history blobs were not deleted after the commit")


async def _history_with_blobs(
    db_session: AsyncSession, tmp_path: Path
) -> tuple[UUID, UUID, LocalObjectStore, list[str]]:
    user_id, project_id, doc_id = await _make_doc(db_session)
    svc = _service(db_session, tmp_path, history_inline_max_bytes=1)  # every payload is offloaded
    ed, updates = _editor()
    ed.replace_text("kept in a blob\n")
    await svc.capture_update(
        project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=user_id, at=_NOW
    )
    await svc.flush_doc(doc_id=doc_id, reason="manual")
    keys = await _blob_keys(db_session, doc_id)
    store = LocalObjectStore(tmp_path, 65536)
    assert keys
    assert all([await store.exists(key) for key in keys])
    return project_id, doc_id, store, keys


async def test_deleting_a_document_deletes_its_offloaded_blobs(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, doc_id, store, keys = await _history_with_blobs(db_session, tmp_path)
    # The composition root registers the purge (app.create_app); a bare session needs it here.
    monkeypatch.setattr(tree_service, "_deletion_listeners", [])
    on_entities_deleted(purge_blobs_for_deleted)

    await tree_service.delete_entity(db_session, project_id, doc_id, store=store)
    await db_session.commit()

    await _wait_until_gone(store, keys)


async def test_rolled_back_delete_keeps_its_blobs(db_session: AsyncSession, tmp_path: Path) -> None:
    _, doc_id, store, keys = await _history_with_blobs(db_session, tmp_path)

    await purge_blobs_after_commit(db_session, store, [doc_id])
    await db_session.rollback()
    await asyncio.sleep(0.05)

    assert all([await store.exists(key) for key in keys])


async def test_failed_blob_delete_is_logged_and_the_others_still_go(
    db_session: AsyncSession, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _, doc_id, store, keys = await _history_with_blobs(db_session, tmp_path)
    failing = keys[0]
    real_delete = store.delete

    async def flaky_delete(key: str) -> None:
        if key == failing:
            raise OSError("object store unavailable")
        await real_delete(key)

    store.delete = flaky_delete  # type: ignore[method-assign]
    await purge_blobs_after_commit(db_session, store, [doc_id])
    await db_session.commit()

    await _wait_until_gone(store, keys[1:])
    assert await store.exists(failing)
    assert any(failing in record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR)
