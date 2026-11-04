"""Integration tests for share links (spec 116): owner routes, preview and join over HTTP.

Shared helpers and the ``enqueuer`` fixture live in ``_sharing_api_support``. The takeback rules
(what turning a link off undoes) are in ``test_share_links_takeback``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth import hash_token
from inkstave.modules.projects.models.project import Project
from inkstave.modules.projects.models.share_link import ProjectShareLink

from ._sharing_api_support import (
    PROJECTS,
    FakeInviteEnqueuer,
    _add_member,
    _auth,
    _project,
    enqueuer,
)

pytestmark = pytest.mark.integration

__all__ = ["enqueuer"]

SHARE_LINKS = "/api/v1/share-links"


async def _create_link(client: AsyncClient, headers: dict[str, str], pid: str, role: str) -> dict[str, Any]:
    r = await client.post(f"{PROJECTS}/{pid}/share-links", json={"role": role}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _error(r: Any) -> dict[str, Any]:
    """The error type and message; the request id differs on every call by design."""
    body = r.json()["error"]
    return {"type": body["type"], "message": body["message"]}


async def _members_by_email(
    client: AsyncClient, headers: dict[str, str], pid: str
) -> dict[str, dict[str, Any]]:
    rows = (await client.get(f"{PROJECTS}/{pid}/members", headers=headers)).json()
    return {m["email"]: m for m in rows}


async def test_owner_turns_on_edit_link_and_stranger_joins(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "editor")
    assert link["role"] == "editor"
    assert link["token"] and link["url"].endswith(f"/join/{link['token']}")

    listed = (await async_client.get(f"{PROJECTS}/{pid}/share-links", headers=owner_h)).json()
    assert [row["id"] for row in listed] == [link["id"]]
    assert "token" not in listed[0] and "url" not in listed[0]  # the token is shown only once

    _, bob_h = await _auth(db_session, email="bob@example.com")
    preview = await async_client.get(f"{SHARE_LINKS}/{link['token']}", headers=bob_h)
    assert preview.status_code == 200, preview.text
    assert preview.json()["project_name"] == "Paper"
    assert preview.json()["role"] == "editor"
    assert preview.json()["already_member_role"] is None

    joined = await async_client.post(f"{SHARE_LINKS}/{link['token']}/join", headers=bob_h)
    assert joined.status_code == 200, joined.text
    assert joined.json() == {"project_id": pid, "role": "editor"}

    # Joining is idempotent: one membership, still editor.
    again = await async_client.post(f"{SHARE_LINKS}/{link['token']}/join", headers=bob_h)
    assert again.json()["role"] == "editor"
    members = await _members_by_email(async_client, owner_h, pid)
    assert members["bob@example.com"]["role"] == "editor"
    assert members["bob@example.com"]["via_link"] is True
    owner_row = next(m for m in members.values() if m["role"] == "owner")
    assert owner_row["via_link"] is False


async def test_create_on_active_role_rotates_and_old_token_stops(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    old = await _create_link(async_client, owner_h, pid, "editor")
    _, bob_h = await _auth(db_session, email="bob@example.com")
    await async_client.post(f"{SHARE_LINKS}/{old['token']}/join", headers=bob_h)

    new = await _create_link(async_client, owner_h, pid, "editor")  # rotate
    assert new["token"] != old["token"]

    # AC2: the old URL answers as invalid, and the member it created is gone.
    stale = await async_client.get(f"{SHARE_LINKS}/{old['token']}", headers=bob_h)
    assert stale.status_code == 404
    assert stale.json()["error"]["message"] == "This link is no longer valid."
    assert (await async_client.get(f"{PROJECTS}/{pid}/permissions", headers=bob_h)).status_code == 404
    assert "bob@example.com" not in await _members_by_email(async_client, owner_h, pid)

    listed = (await async_client.get(f"{PROJECTS}/{pid}/share-links", headers=owner_h)).json()
    assert [row["id"] for row in listed] == [new["id"]]


async def test_turn_off_link_and_second_turn_off_is_404(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "viewer")

    off = await async_client.delete(f"{PROJECTS}/{pid}/share-links/{link['id']}", headers=owner_h)
    assert off.status_code == 204
    assert (await async_client.get(f"{PROJECTS}/{pid}/share-links", headers=owner_h)).json() == []

    gone = await async_client.delete(f"{PROJECTS}/{pid}/share-links/{link['id']}", headers=owner_h)
    assert gone.status_code == 404
    assert gone.json()["error"]["type"] == "share_link_not_found"


async def test_view_and_edit_links_are_independent(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    await _create_link(async_client, owner_h, pid, "viewer")
    await _create_link(async_client, owner_h, pid, "editor")

    listed = (await async_client.get(f"{PROJECTS}/{pid}/share-links", headers=owner_h)).json()
    assert sorted(row["role"] for row in listed) == ["editor", "viewer"]


async def test_link_cannot_grant_owner(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    r = await async_client.post(f"{PROJECTS}/{pid}/share-links", json={"role": "owner"}, headers=owner_h)
    assert r.status_code == 422


async def test_non_owner_gets_403_and_stranger_gets_404(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "viewer")
    _, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com")
    _, eve_h = await _auth(db_session, email="eve@example.com")
    url = f"{PROJECTS}/{pid}/share-links"

    for headers, status, error in ((bob_h, 403, "not_project_owner"), (eve_h, 404, "project_not_found")):
        assert (await async_client.get(url, headers=headers)).status_code == status
        r = await async_client.post(url, json={"role": "editor"}, headers=headers)
        assert r.status_code == status
        assert r.json()["error"]["type"] == error
        r = await async_client.delete(f"{url}/{link['id']}", headers=headers)
        assert r.status_code == status


async def test_revoked_and_unknown_token_both_404(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "viewer")
    await async_client.delete(f"{PROJECTS}/{pid}/share-links/{link['id']}", headers=owner_h)
    _, bob_h = await _auth(db_session, email="bob@example.com")

    revoked = await async_client.get(f"{SHARE_LINKS}/{link['token']}", headers=bob_h)
    unknown = await async_client.get(f"{SHARE_LINKS}/not-a-real-token", headers=bob_h)
    revoked_join = await async_client.post(f"{SHARE_LINKS}/{link['token']}/join", headers=bob_h)
    unknown_join = await async_client.post(f"{SHARE_LINKS}/not-a-real-token/join", headers=bob_h)

    assert revoked.status_code == unknown.status_code == 404
    assert _error(revoked) == _error(unknown)
    assert revoked_join.status_code == unknown_join.status_code == 404
    assert _error(revoked_join) == _error(unknown_join)


async def test_share_link_stores_hash_only(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "editor")

    row = (
        await db_session.execute(select(ProjectShareLink).where(ProjectShareLink.id == UUID(link["id"])))
    ).scalar_one()
    assert row.token_hash == hash_token(link["token"])
    assert link["token"] not in row.token_hash
    assert link["token"] not in {str(v) for v in vars(row).values()}


async def test_deleted_project_answers_404_on_preview_and_join(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "editor")
    await db_session.execute(
        update(Project).where(Project.id == UUID(pid)).values(deleted_at=datetime.now(UTC))
    )
    await db_session.commit()
    _, bob_h = await _auth(db_session, email="bob@example.com")

    assert (await async_client.get(f"{SHARE_LINKS}/{link['token']}", headers=bob_h)).status_code == 404
    assert (await async_client.post(f"{SHARE_LINKS}/{link['token']}/join", headers=bob_h)).status_code == 404


async def test_preview_shows_existing_role(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "editor")
    _, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com", role="viewer")

    preview = (await async_client.get(f"{SHARE_LINKS}/{link['token']}", headers=bob_h)).json()
    assert preview["already_member_role"] == "viewer"


async def test_rate_limit_applies_to_preview_and_join(
    async_client: AsyncClient,
    db_session: AsyncSession,
    enqueuer: FakeInviteEnqueuer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("RATE_LIMIT_SHARE_LINK", "2/300")
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "viewer")
    _, bob_h = await _auth(db_session, email="bob@example.com")

    assert (await async_client.get(f"{SHARE_LINKS}/{link['token']}", headers=bob_h)).status_code == 200
    assert (await async_client.post(f"{SHARE_LINKS}/{link['token']}/join", headers=bob_h)).status_code == 200
    limited = await async_client.get(f"{SHARE_LINKS}/{link['token']}", headers=bob_h)

    assert limited.status_code == 429
    assert limited.json()["error"]["type"] == "rate_limited"
    get_settings.cache_clear()


async def test_raw_token_is_never_logged(
    async_client: AsyncClient,
    db_session: AsyncSession,
    enqueuer: FakeInviteEnqueuer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    link = await _create_link(async_client, owner_h, pid, "editor")
    _, bob_h = await _auth(db_session, email="bob@example.com")
    await async_client.get(f"{SHARE_LINKS}/{link['token']}", headers=bob_h)
    await async_client.post(f"{SHARE_LINKS}/{link['token']}/join", headers=bob_h)

    # httpx logs the URL of its own client calls; the server's own records are what must stay clean.
    server_records = [r.getMessage() for r in caplog.records if not r.name.startswith("httpx")]
    assert server_records
    assert all(link["token"] not in message for message in server_records)
