"""Spec-34 central authorization across REST endpoints (owner/editor/viewer/non-member)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.dependencies import get_compile_enqueuer, get_email_enqueuer
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"


class _FakeEnqueuer:
    async def enqueue(self, job_id: UUID) -> str | None:
        return f"job-{job_id}"

    async def enqueue_email(self, **_kwargs: object) -> str | None:
        return "job-email"


async def _user(db_session: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def _add_member(db_session: AsyncSession, project_id: str, user_id: UUID, role: str) -> None:
    db_session.add(
        ProjectMembership(
            project_id=UUID(project_id),
            user_id=user_id,
            role=role,
            status=MembershipStatus.active,
        )
    )
    await db_session.commit()


@pytest.fixture
async def actors(
    app: Any, async_client: AsyncClient, db_session: AsyncSession
) -> SimpleNamespace:
    # Stub the ARQ enqueuers so sharing/compile routes don't touch real Redis.
    app.dependency_overrides[get_compile_enqueuer] = lambda: _FakeEnqueuer()
    app.dependency_overrides[get_email_enqueuer] = lambda: _FakeEnqueuer()

    owner, owner_h = await _user(db_session)
    pid = (await async_client.post(PROJECTS, json={"name": "P"}, headers=owner_h)).json()["id"]
    doc = await async_client.post(
        f"{PROJECTS}/{pid}/tree/entities",
        json={"type": "doc", "name": "main.tex", "parent_id": None},
        headers=owner_h,
    )
    doc_id = doc.json()["id"]

    editor, editor_h = await _user(db_session)
    await _add_member(db_session, pid, editor.id, MembershipRole.editor)
    viewer, viewer_h = await _user(db_session)
    await _add_member(db_session, pid, viewer.id, MembershipRole.viewer)
    _outsider, outsider_h = await _user(db_session)

    return SimpleNamespace(
        pid=pid,
        doc_id=doc_id,
        owner=owner_h,
        editor=editor_h,
        viewer=viewer_h,
        outsider=outsider_h,
    )


# --- reads: owner/editor/viewer succeed, non-member 404 -------------------- #


async def test_project_read(actors: SimpleNamespace, async_client: AsyncClient) -> None:
    for hdr in (actors.owner, actors.editor, actors.viewer):
        assert (await async_client.get(f"{PROJECTS}/{actors.pid}", headers=hdr)).status_code == 200
    assert (
        await async_client.get(f"{PROJECTS}/{actors.pid}", headers=actors.outsider)
    ).status_code == 404  # AC1


async def test_doc_and_tree_read(actors: SimpleNamespace, async_client: AsyncClient) -> None:
    url = f"{PROJECTS}/{actors.pid}/documents/{actors.doc_id}"
    for hdr in (actors.owner, actors.editor, actors.viewer):  # AC3 viewer reads
        assert (await async_client.get(url, headers=hdr)).status_code == 200
    assert (await async_client.get(url, headers=actors.outsider)).status_code == 404


# --- writes: viewer 403, non-member 404, editor/owner succeed -------------- #


async def test_project_write_is_owner_only(
    actors: SimpleNamespace, async_client: AsyncClient
) -> None:
    url = f"{PROJECTS}/{actors.pid}"
    assert (
        await async_client.patch(url, json={"name": "New"}, headers=actors.editor)
    ).status_code == 403  # AC4 editor denied
    assert (
        await async_client.patch(url, json={"name": "New"}, headers=actors.viewer)
    ).status_code == 403
    assert (
        await async_client.patch(url, json={"name": "New"}, headers=actors.outsider)
    ).status_code == 404
    assert (
        await async_client.patch(url, json={"name": "New"}, headers=actors.owner)
    ).status_code == 200  # AC5


async def test_doc_write(actors: SimpleNamespace, async_client: AsyncClient) -> None:
    url = f"{PROJECTS}/{actors.pid}/documents/{actors.doc_id}"
    # viewer / non-member denied before any version check
    assert (
        await async_client.put(url, json={"content": "x", "base_version": 0}, headers=actors.viewer)
    ).status_code == 403  # AC2 INSUFFICIENT_ROLE
    assert (
        await async_client.put(
            url, json={"content": "x", "base_version": 0}, headers=actors.outsider
        )
    ).status_code == 404
    # editor may write
    version = (await async_client.get(url, headers=actors.editor)).json()["version"]
    ok = await async_client.put(
        url, json={"content": "edited", "base_version": version}, headers=actors.editor
    )
    assert ok.status_code == 200  # AC4 editor writes


async def test_tree_write_is_editor_plus(
    actors: SimpleNamespace, async_client: AsyncClient
) -> None:
    url = f"{PROJECTS}/{actors.pid}/tree/entities"
    body = {"type": "doc", "name": "extra.tex", "parent_id": None}
    assert (await async_client.post(url, json=body, headers=actors.viewer)).status_code == 403
    assert (await async_client.post(url, json=body, headers=actors.outsider)).status_code == 404
    assert (await async_client.post(url, json=body, headers=actors.editor)).status_code == 201


# --- sharing: owner-only --------------------------------------------------- #


async def test_share_is_owner_only(actors: SimpleNamespace, async_client: AsyncClient) -> None:
    url = f"{PROJECTS}/{actors.pid}/invites"
    body = {"email": "new@example.com", "role": "viewer"}
    assert (await async_client.post(url, json=body, headers=actors.editor)).status_code == 403
    assert (await async_client.post(url, json=body, headers=actors.viewer)).status_code == 403
    assert (await async_client.post(url, json=body, headers=actors.outsider)).status_code == 404


# --- compile: members (incl. viewer) allowed, non-member denied ------------ #


async def test_compile_allows_members(
    actors: SimpleNamespace, async_client: AsyncClient
) -> None:
    url = f"{PROJECTS}/{actors.pid}/compile"
    for hdr in (actors.owner, actors.editor, actors.viewer):  # AC9 + viewer-compile default
        resp = await async_client.post(url, json={}, headers=hdr)
        assert resp.status_code == 202, (hdr, resp.text)
    assert (
        await async_client.post(url, json={}, headers=actors.outsider)
    ).status_code == 404


# --- /permissions ---------------------------------------------------------- #


async def test_permissions_per_role(actors: SimpleNamespace, async_client: AsyncClient) -> None:
    url = f"{PROJECTS}/{actors.pid}/permissions"
    owner_perms = (await async_client.get(url, headers=actors.owner)).json()
    assert owner_perms["role"] == "owner" and "project_delete" in owner_perms["capabilities"]

    editor_perms = (await async_client.get(url, headers=actors.editor)).json()
    assert editor_perms["role"] == "editor"
    assert "doc_write" in editor_perms["capabilities"]
    assert "project_delete" not in editor_perms["capabilities"]

    viewer_perms = (await async_client.get(url, headers=actors.viewer)).json()
    assert viewer_perms["role"] == "viewer"
    assert "doc_write" not in viewer_perms["capabilities"]
    assert "collab_write" not in viewer_perms["capabilities"]

    assert (await async_client.get(url, headers=actors.outsider)).status_code == 404  # AC10
