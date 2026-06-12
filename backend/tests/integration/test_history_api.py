"""Integration tests for the history API: versions and updates listing (spec 37).

Diff, labels and auth concerns live in the sibling ``test_history_api_*.py``
modules; shared helpers and the ``hist`` fixture live in ``_history_api_support``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.history import HistoryUpdate

from ._history_api_support import _hist_url, hist

pytestmark = pytest.mark.integration

__all__ = ["hist"]


# --- versions / updates ---------------------------------------------------- #


async def test_list_versions(hist: SimpleNamespace, async_client: AsyncClient) -> None:
    r = await async_client.get(_hist_url(hist.pid, hist.doc_id, "versions"), headers=hist.viewer_h)
    assert r.status_code == 200
    body = r.json()
    assert body["current_version"] == 3
    versions = body["versions"]
    assert [v["version"] for v in versions] == [3, 2, 1]  # newest first (AC1)
    assert versions[0]["author"]["email"]  # author joined
    assert versions[0]["op_count"] >= 1 and versions[0]["size"] > 0


async def test_versions_pagination_and_gaps(
    hist: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    r = await async_client.get(
        _hist_url(hist.pid, hist.doc_id, "versions?limit=2"), headers=hist.owner_h
    )
    body = r.json()
    assert [v["version"] for v in body["versions"]] == [3, 2]
    assert body["has_more"] is True and body["next_before"] == 2

    # Simulate a compaction gap: delete version 2's update row.
    await db_session.execute(
        delete(HistoryUpdate).where(
            HistoryUpdate.doc_id == hist.doc_uuid, HistoryUpdate.version == 2
        )
    )
    await db_session.commit()
    r2 = await async_client.get(
        _hist_url(hist.pid, hist.doc_id, "versions"), headers=hist.owner_h
    )
    assert [v["version"] for v in r2.json()["versions"]] == [3, 1]  # gap tolerated (AC2)


async def test_list_updates_range_and_bad_range(
    hist: SimpleNamespace, async_client: AsyncClient
) -> None:
    r = await async_client.get(
        _hist_url(hist.pid, hist.doc_id, "updates?from=1&to=2"), headers=hist.viewer_h
    )
    assert [u["version"] for u in r.json()["updates"]] == [1, 2]  # ascending
    bad = await async_client.get(
        _hist_url(hist.pid, hist.doc_id, "updates?from=3&to=1"), headers=hist.viewer_h
    )
    assert bad.status_code == 400
