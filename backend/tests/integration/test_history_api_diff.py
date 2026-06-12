"""Integration tests for the history diff route: diffs, binary, size guard, 404 (spec 37/61).

Shared helpers and the ``hist`` fixture live in ``_history_api_support``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.collab.ydocument import YDocument
from inkstave.config import get_settings
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.history.capture import HistoryCaptureService
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.tree_service import create_entity
from inkstave.storage.local import LocalObjectStore

from ._history_api_support import _NOW, _hist_url, hist

pytestmark = pytest.mark.integration

__all__ = ["hist"]


# --- diff ------------------------------------------------------------------ #


async def test_diff_between_versions(hist: SimpleNamespace, async_client: AsyncClient) -> None:
    r = await async_client.get(
        _hist_url(hist.pid, hist.doc_id, "diff?from=1&to=2"), headers=hist.viewer_h
    )
    assert r.status_code == 200
    body = r.json()
    assert body["binary"] is False and body["from"] == 1 and body["to"] == 2
    added = [s["value"] for h in body["hunks"] for s in h["segments"] if s["type"] == "added"]
    assert "line two\n" in added  # AC3: v1 -> v2 added "line two"


async def test_diff_against_current(hist: SimpleNamespace, async_client: AsyncClient) -> None:
    r = await async_client.get(
        _hist_url(hist.pid, hist.doc_id, "diff?from=1&to=current"), headers=hist.editor_h
    )
    assert r.status_code == 200
    body = r.json()
    assert body["to"] == "current" and body["binary"] is False  # AC4
    added = [s["value"] for h in body["hunks"] for s in h["segments"] if s["type"] == "added"]
    assert "LINE TWO\n" in added  # current is v3 text


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def test_diff_binary_document(
    hist: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession, tmp_path: Any
) -> None:
    # A separate doc whose captured text contains a NUL byte (binary). Build it via the
    # capture service directly — the spec-13 content bridge cannot store NUL.
    entity = await create_entity(
        db_session, UUID(hist.pid), TreeEntityType.doc, "bin.tex", None
    )
    await set_content_from_collab(db_session, entity.id, "")
    await db_session.commit()
    svc = HistoryCaptureService(
        lambda: _SessionCtx(db_session),
        LocalObjectStore(tmp_path, 65536),
        get_settings().model_copy(update={"history_debounce_ms": 10_000_000}),
    )
    ed = YDocument()
    updates: list[bytes] = []
    ed.observe(lambda u, _o: updates.append(u))
    ed.replace_text("binary\x00content\n")
    await svc.capture_update(
        project_id=UUID(hist.pid), doc_id=entity.id, update=updates[-1], author_id=None, at=_NOW
    )
    await svc.flush_doc(doc_id=entity.id, reason="manual")

    r = await async_client.get(
        _hist_url(hist.pid, str(entity.id), "diff?from=1&to=current"), headers=hist.viewer_h
    )
    assert r.status_code == 200
    body = r.json()
    assert body["binary"] is True and body["hunks"] == []  # AC5


async def test_diff_missing_version_404(
    hist: SimpleNamespace, async_client: AsyncClient
) -> None:
    # §5.2.3: 404 if either version is not captured. Version 999 does not exist.
    r = await async_client.get(
        _hist_url(hist.pid, hist.doc_id, "diff?from=999&to=current"), headers=hist.viewer_h
    )
    assert r.status_code == 404


async def test_diff_size_guard_413(
    hist: SimpleNamespace, db_session: AsyncSession, tmp_path: Any
) -> None:
    # Service-level: a tiny HISTORY_DIFF_MAX_BYTES routes to the 413/too_large path (AC11).
    from inkstave.history.read import get_diff

    tiny = get_settings().model_copy(update={"history_diff_max_bytes": 1})
    result = await get_diff(
        db_session, hist.comp.history._store, tiny, hist.doc_uuid, from_v=1, to=2
    )
    assert result.too_large is True and result.hunks == []


async def test_diff_route_returns_413_with_full_body(
    hist: SimpleNamespace, app: Any, async_client: AsyncClient
) -> None:
    # HTTP-level (spec 61 AC5): a tiny HISTORY_DIFF_MAX_BYTES makes the diff route
    # respond 413 carrying the FULL diff shape (not an error envelope).
    from inkstave.dependencies import get_settings_dep

    tiny = get_settings().model_copy(update={"history_diff_max_bytes": 1})
    app.dependency_overrides[get_settings_dep] = lambda: tiny
    try:
        r = await async_client.get(
            _hist_url(hist.pid, hist.doc_id, "diff?from=1&to=2"), headers=hist.viewer_h
        )
    finally:
        del app.dependency_overrides[get_settings_dep]
    assert r.status_code == 413
    body = r.json()
    assert body["too_large"] is True
    assert body["hunks"] == []
    assert set(body.keys()) == {"from", "to", "binary", "too_large", "hunks"}
    assert "error" not in body  # not an error envelope
