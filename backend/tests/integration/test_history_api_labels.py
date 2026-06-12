"""Integration tests for the history labels routes and auth (spec 37).

Shared helpers and the ``hist`` fixture live in ``_history_api_support``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity

from ._history_api_support import _hist_url, _user, hist

pytestmark = pytest.mark.integration

__all__ = ["hist"]


# --- labels ---------------------------------------------------------------- #


async def test_labels_crud_and_duplicate(
    hist: SimpleNamespace, async_client: AsyncClient
) -> None:
    url = _hist_url(hist.pid, hist.doc_id, "labels")
    created = await async_client.post(
        url, json={"version": 2, "name": "submitted"}, headers=hist.editor_h
    )
    assert created.status_code == 201 and created.json()["name"] == "submitted"

    listed = (await async_client.get(url, headers=hist.viewer_h)).json()
    assert [label["name"] for label in listed] == ["submitted"]

    dup = await async_client.post(
        url, json={"version": 3, "name": "submitted"}, headers=hist.editor_h
    )
    assert dup.status_code == 409  # AC10 duplicate

    label_id = created.json()["id"]
    deleted = await async_client.delete(f"{url}/{label_id}", headers=hist.editor_h)
    assert deleted.status_code == 204
    assert (await async_client.get(url, headers=hist.viewer_h)).json() == []


async def test_label_shows_in_versions(hist: SimpleNamespace, async_client: AsyncClient) -> None:
    url = _hist_url(hist.pid, hist.doc_id, "labels")
    await async_client.post(url, json={"version": 3, "name": "final"}, headers=hist.owner_h)
    versions = (
        await async_client.get(_hist_url(hist.pid, hist.doc_id, "versions"), headers=hist.owner_h)
    ).json()["versions"]
    v3 = next(v for v in versions if v["version"] == 3)
    assert [label["name"] for label in v3["labels"]] == ["final"]


# --- auth ------------------------------------------------------------------ #


async def test_viewer_cannot_label_or_restore(
    hist: SimpleNamespace, async_client: AsyncClient
) -> None:
    label = await async_client.post(
        _hist_url(hist.pid, hist.doc_id, "labels"), json={"version": 1, "name": "x"},
        headers=hist.viewer_h,
    )
    assert label.status_code == 403  # AC8 viewer denied
    restore = await async_client.post(
        _hist_url(hist.pid, hist.doc_id, "restore"), json={"version": 1}, headers=hist.viewer_h
    )
    assert restore.status_code == 403


async def test_non_member_gets_404(hist: SimpleNamespace, async_client: AsyncClient) -> None:
    r = await async_client.get(
        _hist_url(hist.pid, hist.doc_id, "versions"), headers=hist.outsider_h
    )
    assert r.status_code == 404  # AC8 non-member, no existence leak


async def test_delete_missing_label_404(
    hist: SimpleNamespace, async_client: AsyncClient
) -> None:
    from uuid import uuid4

    r = await async_client.delete(
        _hist_url(hist.pid, hist.doc_id, f"labels/{uuid4()}"), headers=hist.editor_h
    )
    assert r.status_code == 404  # AC10: not-found branch (random UUID)


async def test_delete_cross_project_label_404(
    hist: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # A real label belonging to project B, accessed via project A's URL with a
    # token authorized on A, must 404 (cross-project access, not just not-found).
    owner_b, owner_b_h = await _user(db_session)
    project_b = await create_project(db_session, owner_b.id, "B")
    entity_b = await create_entity(
        db_session, project_b.id, TreeEntityType.doc, "main.tex", None
    )
    await set_content_from_collab(db_session, entity_b.id, "")
    await db_session.commit()

    created = await async_client.post(
        _hist_url(str(project_b.id), str(entity_b.id), "labels"),
        json={"version": 1, "name": "from-b"},
        headers=owner_b_h,
    )
    assert created.status_code == 201
    label_b_id = created.json()["id"]

    # DELETE via project A's URL (its own doc) with project A's owner token.
    r = await async_client.delete(
        _hist_url(hist.pid, hist.doc_id, f"labels/{label_b_id}"), headers=hist.owner_h
    )
    assert r.status_code == 404  # AC10: wrong-project label is not visible from A
