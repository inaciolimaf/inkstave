"""Integration tests for the project chat API (spec 117)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.db.session import get_db_session
from inkstave.modules.discussion.models import ProjectChatMessage
from tests.integration._discussion_support import (
    chat_url,
    failing_commit_session,
    next_event,
    no_event,
    post_message,
    subscribe,
)
from tests.integration._sharing_api_support import _add_member, _auth, _project

pytestmark = pytest.mark.integration


async def _room(client: AsyncClient, db_session: AsyncSession) -> dict[str, Any]:
    """A project with an owner, an editor and a viewer, each with their headers."""
    owner, owner_h = await _auth(db_session)
    pid = await _project(client, owner_h)
    editor, editor_h = await _add_member(client, db_session, owner_h, pid, "ed@example.com", "editor")
    viewer, viewer_h = await _add_member(client, db_session, owner_h, pid, "vi@example.com", "viewer")
    return {
        "pid": pid,
        "owner": (owner, owner_h),
        "editor": (editor, editor_h),
        "viewer": (viewer, viewer_h),
    }


async def test_post_then_list_round_trip(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid, (owner, owner_h) = room["pid"], room["owner"]

    created = await post_message(async_client, owner_h, pid, "Oi")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["body"] == "Oi"
    assert body["deleted"] is False
    assert body["author"] == {"id": str(owner.id), "display_name": owner.display_name}

    page = (await async_client.get(f"{chat_url(pid)}/messages", headers=owner_h)).json()
    assert [m["id"] for m in page["items"]] == [body["id"]]
    assert page["has_more"] is False


async def test_viewer_can_read_and_post(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid, (_, viewer_h) = room["pid"], room["viewer"]

    assert (await post_message(async_client, viewer_h, pid, "from a viewer")).status_code == 201
    listing = await async_client.get(f"{chat_url(pid)}/messages", headers=viewer_h)
    assert listing.status_code == 200
    assert listing.json()["items"][0]["body"] == "from a viewer"


async def test_stranger_gets_404_on_every_route(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid = room["pid"]
    _, stranger_h = await _auth(db_session, email="stranger@example.com")
    message_id = uuid4()
    calls = [
        async_client.get(f"{chat_url(pid)}/messages", headers=stranger_h),
        post_message(async_client, stranger_h, pid, "hi"),
        async_client.delete(f"{chat_url(pid)}/messages/{message_id}", headers=stranger_h),
        async_client.get(f"{chat_url(pid)}/unread", headers=stranger_h),
        async_client.post(f"{chat_url(pid)}/read", headers=stranger_h),
    ]
    for call in calls:
        response = await call
        assert response.status_code == 404, response.text
        assert response.json()["error"]["type"] == "project_not_found"


async def test_anonymous_gets_401(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    response = await async_client.get(f"{chat_url(room['pid'])}/messages")
    assert response.status_code == 401


@pytest.mark.parametrize("body", ["", "   \n\t ", "x" * 4001])
async def test_invalid_bodies_are_422(async_client: AsyncClient, db_session: AsyncSession, body: str) -> None:
    room = await _room(async_client, db_session)
    response = await post_message(async_client, room["owner"][1], room["pid"], body)
    assert response.status_code == 422, response.text


async def test_longest_body_is_accepted_and_stored_trimmed(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    response = await post_message(async_client, room["owner"][1], room["pid"], "  " + "x" * 4000 + "  ")
    assert response.status_code == 201
    assert response.json()["body"] == "x" * 4000


async def _seed_messages(db_session: AsyncSession, pid: str, author_id: Any, count: int) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    db_session.add_all(
        [
            ProjectChatMessage(
                project_id=UUID(pid),
                author_id=author_id,
                body=f"message {i}",
                created_at=base + timedelta(seconds=i),
            )
            for i in range(count)
        ]
    )
    await db_session.flush()


async def test_paging_is_newest_first_without_duplicates(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, (owner, owner_h) = room["pid"], room["owner"]
    await _seed_messages(db_session, pid, owner.id, 55)

    first = (await async_client.get(f"{chat_url(pid)}/messages", headers=owner_h)).json()
    assert len(first["items"]) == 50
    assert first["has_more"] is True
    assert first["items"][0]["body"] == "message 54"

    oldest_shown = first["items"][-1]["id"]
    second = (
        await async_client.get(f"{chat_url(pid)}/messages", params={"before": oldest_shown}, headers=owner_h)
    ).json()
    assert [m["body"] for m in second["items"]] == [f"message {i}" for i in range(4, -1, -1)]
    assert second["has_more"] is False

    ids = [m["id"] for m in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 55


async def test_unknown_or_foreign_cursor_is_404(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    other = await _project(async_client, room["owner"][1], name="Other")
    foreign = (await post_message(async_client, room["owner"][1], other, "elsewhere")).json()["id"]
    pid, owner_h = room["pid"], room["owner"][1]

    for cursor in (str(uuid4()), foreign):
        response = await async_client.get(
            f"{chat_url(pid)}/messages", params={"before": cursor}, headers=owner_h
        )
        assert response.status_code == 404
        assert response.json()["error"]["type"] == "chat_message_not_found"


async def test_unread_counts_others_until_the_chat_is_opened(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, owner_h, editor_h = room["pid"], room["owner"][1], room["editor"][1]

    await post_message(async_client, owner_h, pid, "Oi")
    unread = f"{chat_url(pid)}/unread"
    assert (await async_client.get(unread, headers=editor_h)).json() == {"count": 1}
    assert (await async_client.get(unread, headers=owner_h)).json() == {"count": 0}

    assert (await async_client.post(f"{chat_url(pid)}/read", headers=editor_h)).status_code == 204
    assert (await async_client.get(unread, headers=editor_h)).json() == {"count": 0}

    await post_message(async_client, owner_h, pid, "again")
    assert (await async_client.get(unread, headers=editor_h)).json() == {"count": 1}


async def test_only_the_author_deletes_and_deletion_is_soft(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, owner_h, editor_h = room["pid"], room["owner"][1], room["editor"][1]
    message_id = (await post_message(async_client, owner_h, pid, "to delete")).json()["id"]
    url = f"{chat_url(pid)}/messages/{message_id}"

    refused = await async_client.delete(url, headers=editor_h)
    assert refused.status_code == 403
    assert refused.json()["error"]["type"] == "not_message_author"

    assert (await async_client.delete(url, headers=owner_h)).status_code == 204
    assert (await async_client.delete(url, headers=owner_h)).status_code == 204  # idempotent

    page = (await async_client.get(f"{chat_url(pid)}/messages", headers=editor_h)).json()
    assert page["items"][0]["deleted"] is True
    assert page["items"][0]["body"] is None
    assert page["items"][0]["id"] == message_id
    assert (await async_client.get(f"{chat_url(pid)}/unread", headers=editor_h)).json() == {"count": 0}


async def test_delete_of_missing_message_is_404(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    url = f"{chat_url(room['pid'])}/messages/{uuid4()}"
    response = await async_client.delete(url, headers=room["owner"][1])
    assert response.status_code == 404
    assert response.json()["error"]["type"] == "chat_message_not_found"


async def test_posting_is_capped_per_user_per_project(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, owner_h = room["pid"], room["owner"][1]
    for i in range(30):
        assert (await post_message(async_client, owner_h, pid, f"m{i}")).status_code == 201

    limited = await post_message(async_client, owner_h, pid, "one too many")
    assert limited.status_code == 429
    assert limited.json()["error"]["type"] == "rate_limited"
    assert "Retry-After" in limited.headers


async def test_event_is_published_after_the_commit(
    async_client: AsyncClient, db_session: AsyncSession, redis: Any
) -> None:
    room = await _room(async_client, db_session)
    pid, owner_h = room["pid"], room["owner"][1]
    pubsub = await subscribe(redis, UUID(pid))

    message_id = (await post_message(async_client, owner_h, pid, "Oi")).json()["id"]
    created = await next_event(pubsub)
    assert created["type"] == "chat.message_created"
    assert created["payload"]["id"] == message_id
    assert created["payload"]["body"] == "Oi"

    await async_client.delete(f"{chat_url(pid)}/messages/{message_id}", headers=owner_h)
    deleted = await next_event(pubsub)
    assert deleted["type"] == "chat.message_deleted"
    assert deleted["payload"] == {"id": message_id}
    assert deleted["id"] > created["id"]


async def test_event_not_published_on_rollback(
    async_client: AsyncClient, db_session: AsyncSession, app: Any, redis: Any
) -> None:
    room = await _room(async_client, db_session)
    pid, owner_h = room["pid"], room["owner"][1]
    pubsub = await subscribe(redis, UUID(pid))
    app.dependency_overrides[get_db_session] = failing_commit_session(db_session)

    response = await post_message(async_client, owner_h, pid, "never committed")
    assert response.status_code == 500
    assert await no_event(pubsub)
