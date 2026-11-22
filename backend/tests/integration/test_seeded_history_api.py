"""History API on a document that existed before history did: list, diff and restore after its first edits."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.collab.ws.components import CollabComponents
from tests.collab_ws_harness import install_collab
from tests.factories.lived_in import APPENDIX_TEX, LivedInProject
from tests.integration._seeded_support import auth_headers, edit_over_socket

pytestmark = pytest.mark.integration

FIRST = APPENDIX_TEX.replace("Written before history existed.", "First edit, seeded doc.")
SECOND = FIRST.replace("First edit", "Second edit")


@pytest.fixture
def components(app: Any, db_session: AsyncSession, redis: Any) -> CollabComponents:
    return install_collab(app, db_session, redis, history_debounce_ms=10_000_000)


def _url(lived: LivedInProject, suffix: str) -> str:
    return f"/api/v1/projects/{lived.project_id}/docs/{lived.ids['appendix.tex']}/history/{suffix}"


async def _two_edits(app: Any, components: CollabComponents, lived: LivedInProject) -> None:
    doc_id = lived.ids["appendix.tex"]
    await edit_over_socket(app, components, lived.project_id, doc_id, lived.owner, FIRST)
    await edit_over_socket(app, components, lived.project_id, doc_id, lived.owner, SECOND)


async def test_seeded_older_document_lists_its_versions(
    app: Any, async_client: AsyncClient, components: CollabComponents, lived_in_project: LivedInProject
) -> None:
    await edit_over_socket(
        app,
        components,
        lived_in_project.project_id,
        lived_in_project.ids["appendix.tex"],
        lived_in_project.owner,
        FIRST,
    )
    headers = auth_headers(lived_in_project.owner)

    resp = await async_client.get(_url(lived_in_project, "versions"), headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert [entry["version"] for entry in body["versions"]] == [1]
    assert body["current_version"] == 1


async def test_seeded_older_document_diff_shows_only_the_edit(
    app: Any, async_client: AsyncClient, components: CollabComponents, lived_in_project: LivedInProject
) -> None:
    await _two_edits(app, components, lived_in_project)
    headers = auth_headers(lived_in_project.owner)

    resp = await async_client.get(
        _url(lived_in_project, "diff"), params={"from": 1, "to": "current"}, headers=headers
    )

    assert resp.status_code == 200
    segments = [segment for hunk in resp.json()["hunks"] for segment in hunk["segments"]]
    added = [s["value"] for s in segments if s["type"] == "added"]
    removed = [s["value"] for s in segments if s["type"] == "removed"]
    # The text before the edit is shown as context, not as a block added to the file.
    assert any("\\appendix" in s["value"] for s in segments if s["type"] == "context")
    assert any("Second edit" in value for value in added)
    assert any("First edit" in value for value in removed)


async def test_seeded_older_document_restores_an_earlier_version(
    app: Any,
    async_client: AsyncClient,
    components: CollabComponents,
    db_session: AsyncSession,
    lived_in_project: LivedInProject,
) -> None:
    await _two_edits(app, components, lived_in_project)
    headers = auth_headers(lived_in_project.owner)

    resp = await async_client.post(_url(lived_in_project, "restore"), json={"version": 1}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["restored_from_version"] == 1
    content = await async_client.get(
        f"/api/v1/projects/{lived_in_project.project_id}/documents/{lived_in_project.ids['appendix.tex']}",
        headers=headers,
    )
    assert content.json()["content"] == FIRST
