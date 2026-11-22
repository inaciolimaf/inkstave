"""Export, rename, move and delete on a lived-in project: every seeded file survives each operation."""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.projects.models.project import Project
from tests.factories.lived_in import DOC_CONTENTS, FILE_PATH, PLOT_PNG, LivedInProject
from tests.integration._seeded_support import auth_headers

pytestmark = pytest.mark.integration


def _project_url(lived: LivedInProject, suffix: str = "") -> str:
    return f"/api/v1/projects/{lived.project_id}{suffix}"


def _node_id(tree: dict[str, Any], path: str) -> str:
    """The id of the tree node at ``path``, searched through the nested ``children`` lists."""
    stack = [tree["root"]]
    while stack:
        node = stack.pop()
        if node["path"] == path:
            return str(node["id"])
        stack.extend(node.get("children") or [])
    raise AssertionError(f"no tree node at {path!r}")


async def test_seeded_export_zip_holds_every_file_byte_identical(
    async_client: AsyncClient, lived_in_project: LivedInProject
) -> None:
    resp = await async_client.get(
        _project_url(lived_in_project, "/export.zip"), headers=auth_headers(lived_in_project.owner)
    )

    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = set(archive.namelist())
        for path, text in DOC_CONTENTS.items():
            assert archive.read(path) == text.encode("utf-8"), path
        assert archive.read(FILE_PATH) == PLOT_PNG
    assert {*DOC_CONTENTS, FILE_PATH} <= names


async def _rename_and_move(async_client: AsyncClient, lived: LivedInProject, headers: dict[str, str]) -> None:
    """Rename ``chapters/intro.tex`` and move ``appendix.tex`` into ``chapters``."""
    intro_id = str(lived.ids["chapters/intro.tex"])
    appendix_id = str(lived.ids["appendix.tex"])
    renamed = await async_client.patch(
        _project_url(lived, f"/tree/entities/{intro_id}/rename"),
        json={"name": "introduction.tex"},
        headers=headers,
    )
    moved = await async_client.patch(
        _project_url(lived, f"/tree/entities/{appendix_id}/move"),
        json={"new_parent_id": str(lived.folder_ids["chapters"])},
        headers=headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert moved.status_code == 200, moved.text


async def test_seeded_rename_and_move_keep_content_and_comments(
    async_client: AsyncClient, lived_in_project: LivedInProject
) -> None:
    headers = auth_headers(lived_in_project.owner)
    intro_id = str(lived_in_project.ids["chapters/intro.tex"])
    appendix_id = str(lived_in_project.ids["appendix.tex"])
    await _rename_and_move(async_client, lived_in_project, headers)

    tree = (await async_client.get(_project_url(lived_in_project, "/tree"), headers=headers)).json()
    assert _node_id(tree, "chapters/introduction.tex") == intro_id
    assert _node_id(tree, "chapters/appendix.tex") == appendix_id

    for doc_id, path in ((intro_id, "chapters/intro.tex"), (appendix_id, "appendix.tex")):
        content = await async_client.get(
            _project_url(lived_in_project, f"/documents/{doc_id}"), headers=headers
        )
        assert content.json()["content"] == DOC_CONTENTS[path], path

    comments = await async_client.get(
        _project_url(lived_in_project, "/comments"), params={"document_id": intro_id}, headers=headers
    )
    threads = comments.json()["items"]
    assert [t["id"] for t in threads] == [str(lived_in_project.thread_id)]
    assert threads[0]["messages"][0]["body"] == "Is 'seeded' the right word here?"


async def test_seeded_delete_project_hides_it_from_owner_and_collaborator(
    async_client: AsyncClient, db_session: AsyncSession, lived_in_project: LivedInProject
) -> None:
    owner = auth_headers(lived_in_project.owner)
    collaborator = auth_headers(lived_in_project.collaborator)
    assert (
        await async_client.get(_project_url(lived_in_project, "/tree"), headers=collaborator)
    ).status_code == 200

    deleted = await async_client.delete(_project_url(lived_in_project), headers=owner)

    assert deleted.status_code == 204
    for headers in (owner, collaborator):
        assert (await async_client.get(_project_url(lived_in_project), headers=headers)).status_code == 404
        assert (
            await async_client.get(_project_url(lived_in_project, "/tree"), headers=headers)
        ).status_code == 404
        assert (
            await async_client.get(_project_url(lived_in_project, "/export.zip"), headers=headers)
        ).status_code == 404
    listing = await async_client.get("/api/v1/projects", headers=owner)
    assert str(lived_in_project.project_id) not in {p["id"] for p in listing.json()["items"]}
    row = await db_session.get(Project, lived_in_project.project_id)
    assert row is not None and row.deleted_at is not None
