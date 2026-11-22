"""A failed history flush keeps its buffered updates and the next flush writes them (spec 36 hardening)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.history.models import HistoryUpdate
from inkstave.modules.history.versions.capture import HistoryCaptureService
from tests.integration.test_history_capture import _NOW, _count, _editor, _make_doc, _service, _text

pytestmark = pytest.mark.integration


def _fail_first_commit(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the next commit roll back and raise, as a lost database connection does."""
    real_commit = db_session.commit
    attempts = {"n": 0}

    async def flaky_commit() -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            await db_session.rollback()
            raise RuntimeError("database connection lost")
        await real_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)


async def _capture_two_edits(svc: HistoryCaptureService, ids: tuple[UUID, UUID, UUID]) -> None:
    user_id, project_id, doc_id = ids
    ed, updates = _editor()
    ed.replace_text("one\n")
    ed.replace_text("one\ntwo\n")
    for update in updates:
        await svc.capture_update(
            project_id=project_id, doc_id=doc_id, update=update, author_id=user_id, at=_NOW
        )


async def test_failed_flush_keeps_buffer_and_next_flush_persists(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = await _make_doc(db_session)
    doc_id = ids[2]
    svc = _service(db_session, tmp_path)
    await _capture_two_edits(svc, ids)
    _fail_first_commit(db_session, monkeypatch)

    with pytest.raises(RuntimeError):
        await svc.flush_doc(doc_id=doc_id, reason="manual")
    assert await _count(db_session, HistoryUpdate, doc_id) == 0

    await svc.flush_doc(doc_id=doc_id, reason="manual")  # retried, not lost

    assert await _count(db_session, HistoryUpdate, doc_id) == 1
    assert _text(await svc.reconstruct_state(doc_id=doc_id, version=1)) == "one\ntwo\n"
