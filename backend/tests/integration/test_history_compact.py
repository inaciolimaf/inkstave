"""Integration tests for the history compaction job (spec 36, AC7) + migration."""

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
from inkstave.db.models.history import HistoryUpdate
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.history.capture import HistoryCaptureService
from inkstave.history.jobs import compact_history
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from inkstave.storage.local import LocalObjectStore
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 10, tzinfo=UTC)


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def _make_doc(db_session: AsyncSession) -> tuple[UUID, UUID]:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "")
    await db_session.commit()
    return project.id, entity.id


def _settings(**overrides: Any) -> Any:
    return get_settings().model_copy(update={"history_debounce_ms": 10_000_000, **overrides})


def _ctx(db_session: AsyncSession, store: Any, settings: Any) -> dict[str, Any]:
    return {
        "settings": settings,
        "session_factory": lambda: _SessionCtx(db_session),
        "object_store": store,
    }


def _text(state: bytes) -> str:
    doc = YDocument()
    doc.apply_update(state)
    return doc.text


async def _build_sealed_chunk(
    db_session: AsyncSession, store: Any, project_id: UUID, doc_id: UUID
) -> HistoryCaptureService:
    """3 tiny updates → one sealed chunk (v1..v3) + a fresh open chunk."""
    svc = HistoryCaptureService(
        lambda: _SessionCtx(db_session), store, _settings(history_chunk_max_updates=3)
    )
    ed = YDocument()
    updates: list[bytes] = []
    ed.observe(lambda u, _o: updates.append(u))
    for t in ("x", "xx", "xxx"):
        ed.replace_text(t)
        await svc.capture_update(
            project_id=project_id, doc_id=doc_id, update=updates[-1], author_id=None, at=_NOW
        )
        await svc.flush_doc(doc_id=doc_id, reason="manual")
    return svc


async def test_compaction_merges_and_is_idempotent(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    project_id, doc_id = await _make_doc(db_session)
    store = LocalObjectStore(tmp_path, 65536)
    svc = await _build_sealed_chunk(db_session, store, project_id, doc_id)

    before = _text(await svc.reconstruct_state(doc_id=doc_id, version=3))
    rows_before = int(
        await db_session.scalar(
            select(func.count()).select_from(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id)
        )
    )

    result = await compact_history(_ctx(db_session, store, _settings()), str(doc_id))
    assert result["merged_rows"] >= 1  # AC7: rows merged

    rows_after = int(
        await db_session.scalar(
            select(func.count()).select_from(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id)
        )
    )
    assert rows_after < rows_before
    # The kept version reconstructs to the same final state.
    assert _text(await svc.reconstruct_state(doc_id=doc_id, version=3)) == before

    # Re-running is a no-op (idempotent).
    again = await compact_history(_ctx(db_session, store, _settings()), str(doc_id))
    assert again["merged_rows"] == 0
    rows_idem = int(
        await db_session.scalar(
            select(func.count()).select_from(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id)
        )
    )
    assert rows_idem == rows_after


async def test_compaction_offloads_oversized(db_session: AsyncSession, tmp_path: Path) -> None:
    project_id, doc_id = await _make_doc(db_session)
    store = LocalObjectStore(tmp_path, 65536)
    await _build_sealed_chunk(db_session, store, project_id, doc_id)

    # merge_bytes=0 disables merging so we isolate offload; inline_max=5 offloads everything.
    settings = _settings(history_compact_merge_bytes=0, history_inline_max_bytes=5)
    result = await compact_history(_ctx(db_session, store, settings), str(doc_id))
    assert result["offloaded"] >= 1  # AC4 via compaction

    inline_left = int(
        await db_session.scalar(
            select(func.count())
            .select_from(HistoryUpdate)
            .where(HistoryUpdate.doc_id == doc_id, HistoryUpdate.payload.is_not(None))
        )
    )
    assert inline_left == 0  # all update payloads offloaded


async def test_sweep_finds_docs_over_min_updates(db_session: AsyncSession, tmp_path: Path) -> None:
    project_id, doc_id = await _make_doc(db_session)
    store = LocalObjectStore(tmp_path, 65536)
    await _build_sealed_chunk(db_session, store, project_id, doc_id)  # 3 updates

    # doc_id=None sweep with a low threshold should pick up this doc.
    ctx = _ctx(db_session, store, _settings(history_compact_min_updates=2))
    result = await compact_history(ctx)
    assert result["docs"] >= 1

    # AC10 (migration upgrade/downgrade round-trip + no model drift) is covered by
    # the existing tests/integration/test_migrations.py against the full chain,
    # which now includes the history migration.
