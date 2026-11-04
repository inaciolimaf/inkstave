"""Integration tests for comment threads (spec 118): routes, rules, mentions, the bell, e-mail and events."""

from __future__ import annotations

import base64
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.db.session import get_db_session
from inkstave.modules.collab.models import CrdtUpdate
from inkstave.modules.discussion.comments.models import CommentThread
from tests.integration._discussion_support import failing_commit_session, next_event, no_event, subscribe
from tests.integration._sharing_api_support import (  # enqueuer is a fixture, imported for pytest
    FakeInviteEnqueuer,
    _add_member,
    _auth,
    _project,
    enqueuer,
)
from tests.integration._tree_api_support import _create

pytestmark = pytest.mark.integration
__all__ = ["enqueuer"]  # the e-mail fixture, re-exported for pytest as the sibling sharing tests do


def _anchor(seed: int, size: int = 20) -> str:
    return base64.b64encode(bytes([seed]) * size).decode("ascii")


def _comments(pid: str) -> str:
    return f"/api/v1/projects/{pid}/comments"


async def _doc(client: AsyncClient, pid: str, headers: dict[str, str], name: str = "main.tex") -> str:
    created = await _create(client, pid, headers, type_="doc", name=name)
    assert created["status"] == 201, created
    return str(created["json"]["id"])  # type: ignore[index]


async def _room(client: AsyncClient, db_session: AsyncSession) -> dict[str, Any]:
    owner, owner_h = await _auth(db_session)
    pid = await _project(client, owner_h)
    editor, editor_h = await _add_member(client, db_session, owner_h, pid, "ed@example.com", "editor")
    viewer, viewer_h = await _add_member(client, db_session, owner_h, pid, "vi@example.com", "viewer")
    doc = await _doc(client, pid, owner_h)
    return {
        "pid": pid,
        "doc": doc,
        "owner": (owner, owner_h),
        "editor": (editor, editor_h),
        "viewer": (viewer, viewer_h),
    }


def _new_thread(
    doc: str, body: str = "Please check this", mentions: list[UUID] | None = None
) -> dict[str, Any]:
    return {
        "document_id": doc,
        "anchor_start": _anchor(1),
        "anchor_end": _anchor(2),
        "quoted_text": "the results",
        "body": body,
        "mentions": [str(m) for m in mentions or []],
    }


async def _start(
    client: AsyncClient, pid: str, headers: dict[str, str], doc: str, body: str = "First"
) -> Any:
    response = await client.post(_comments(pid), json=_new_thread(doc, body), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _reply(client: AsyncClient, pid: str, headers: dict[str, str], thread: str, body: str) -> Any:
    url = f"{_comments(pid)}/{thread}/messages"
    response = await client.post(url, json={"body": body, "mentions": []}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _bell(client: AsyncClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    """The comment rows of the bell; the invites that room setup sends are not part of these tests."""
    response = await client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return [item for item in response.json()["items"] if item["type"].startswith("comment_")]


def _mails(enqueuer: FakeInviteEnqueuer) -> list[dict[str, Any]]:
    return [call for call in enqueuer.calls if call["template"] == "comment_mention"]


async def test_viewer_can_comment_and_strangers_get_404(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, doc = room["pid"], room["doc"]
    viewer_h = room["viewer"][1]
    thread = await _start(async_client, pid, viewer_h, doc)
    assert thread["messages"][0]["author"]["id"] == str(room["viewer"][0].id)

    _, stranger_h = await _auth(db_session, email="stranger@example.com")
    thread_id = thread["id"]
    calls = [
        async_client.get(_comments(pid), headers=stranger_h),
        async_client.post(_comments(pid), json=_new_thread(doc), headers=stranger_h),
        async_client.post(f"{_comments(pid)}/{thread_id}/messages", json={"body": "hi"}, headers=stranger_h),
        async_client.post(f"{_comments(pid)}/{thread_id}/resolve", headers=stranger_h),
        async_client.post(f"{_comments(pid)}/{thread_id}/reopen", headers=stranger_h),
        async_client.delete(f"{_comments(pid)}/{thread_id}/messages/{uuid4()}", headers=stranger_h),
    ]
    for call in calls:
        response = await call
        assert response.status_code == 404, response.text
        assert response.json()["error"]["type"] == "project_not_found"


async def test_list_filters_by_status_and_document(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, doc, owner_h = room["pid"], room["doc"], room["owner"][1]
    other_doc = await _doc(async_client, pid, owner_h, name="other.tex")
    open_thread = await _start(async_client, pid, owner_h, doc, "open one")
    resolved = await _start(async_client, pid, owner_h, doc, "to resolve")
    await async_client.post(f"{_comments(pid)}/{resolved['id']}/resolve", headers=owner_h)
    elsewhere = await _start(async_client, pid, owner_h, other_doc, "elsewhere")

    async def listed(params: dict[str, str]) -> set[str]:
        response = await async_client.get(_comments(pid), params=params, headers=owner_h)
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()["items"]}

    assert await listed({"status": "open"}) == {open_thread["id"], elsewhere["id"]}
    assert await listed({"status": "resolved"}) == {resolved["id"]}
    assert await listed({"status": "all", "document_id": doc}) == {open_thread["id"], resolved["id"]}


async def test_anchors_round_trip_and_bad_anchors_are_422(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, doc, owner_h = room["pid"], room["doc"], room["owner"][1]
    thread = await _start(async_client, pid, owner_h, doc)
    assert thread["anchor_start"] == _anchor(1)
    assert thread["anchor_end"] == _anchor(2)
    assert thread["quoted_text"] == "the results"

    too_long = {**_new_thread(doc), "anchor_start": _anchor(3, size=257)}
    not_base64 = {**_new_thread(doc), "anchor_end": "not base64!!"}
    too_quoted = {**_new_thread(doc), "quoted_text": "q" * 501}
    for payload in (too_long, not_base64, too_quoted):
        response = await async_client.post(_comments(pid), json=payload, headers=owner_h)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["type"] == "validation_error"


async def test_only_text_documents_take_comments(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid, owner_h = room["pid"], room["owner"][1]
    folder = await _create(async_client, pid, owner_h, type_="folder", name="figures")
    folder_id = str(folder["json"]["id"])  # type: ignore[index]

    response = await async_client.post(_comments(pid), json=_new_thread(folder_id), headers=owner_h)
    assert response.status_code == 422
    assert response.json()["error"]["type"] == "not_a_text_document"

    unknown = await async_client.post(_comments(pid), json=_new_thread(str(uuid4())), headers=owner_h)
    assert unknown.status_code == 404


async def test_author_edits_and_deletes_own_messages(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, doc = room["pid"], room["doc"]
    owner_h, viewer_h = room["owner"][1], room["viewer"][1]
    thread = await _start(async_client, pid, owner_h, doc)
    reply = await _reply(async_client, pid, viewer_h, thread["id"], "Looks wrong")
    message_url = f"{_comments(pid)}/{thread['id']}/messages/{reply['id']}"

    forbidden = await async_client.patch(message_url, json={"body": "mine now"}, headers=owner_h)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["type"] == "not_message_author"
    assert (await async_client.delete(message_url, headers=owner_h)).status_code == 403

    edited = await async_client.patch(message_url, json={"body": "Looks right"}, headers=viewer_h)
    assert edited.status_code == 200, edited.text
    assert edited.json()["body"] == "Looks right"
    assert edited.json()["edited_at"] is not None

    deleted = await async_client.delete(message_url, headers=viewer_h)
    assert deleted.status_code == 204
    again = await async_client.delete(message_url, headers=viewer_h)
    assert again.status_code == 204
    listing = (await async_client.get(_comments(pid), headers=owner_h)).json()["items"]
    messages = listing[0]["messages"]
    assert [m["deleted"] for m in messages] == [False, True]
    assert messages[1]["body"] is None


async def test_deleting_the_only_live_message_deletes_the_thread(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, doc, owner_h = room["pid"], room["doc"], room["owner"][1]
    thread = await _start(async_client, pid, owner_h, doc)
    message_id = thread["messages"][0]["id"]

    response = await async_client.delete(
        f"{_comments(pid)}/{thread['id']}/messages/{message_id}", headers=owner_h
    )
    assert response.status_code == 204
    assert (await async_client.get(_comments(pid), headers=owner_h)).json()["items"] == []
    remaining = await db_session.scalar(select(func.count()).select_from(CommentThread))
    assert remaining == 0


async def test_resolve_and_reopen_by_a_writer(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid, doc = room["pid"], room["doc"]
    editor, editor_h = room["editor"]
    thread = await _start(async_client, pid, room["owner"][1], doc)
    base = f"{_comments(pid)}/{thread['id']}"

    resolved = await async_client.post(f"{base}/resolve", headers=editor_h)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved_by"]["id"] == str(editor.id)
    again = await async_client.post(f"{base}/resolve", headers=editor_h)
    assert again.status_code == 200

    reopened = await async_client.post(f"{base}/reopen", headers=room["viewer"][1])
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None
    assert reopened.json()["resolved_by"] is None


async def test_mentions_filtered_to_members(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid, doc = room["pid"], room["doc"]
    owner, owner_h = room["owner"]
    viewer = room["viewer"][0]
    stranger, stranger_h = await _auth(db_session, email="stranger@example.com")

    payload = _new_thread(doc, "@viewer please check", mentions=[viewer.id, stranger.id, owner.id, uuid4()])
    response = await async_client.post(_comments(pid), json=payload, headers=owner_h)
    assert response.status_code == 201, response.text
    assert response.json()["messages"][0]["mentions"] == [str(viewer.id)]

    assert [n["type"] for n in await _bell(async_client, room["viewer"][1])] == ["comment_mention"]
    assert await _bell(async_client, owner_h) == []
    assert await _bell(async_client, stranger_h) == []


async def test_mention_notifies_in_the_bell_and_by_email(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    room = await _room(async_client, db_session)
    pid, doc = room["pid"], room["doc"]
    viewer, viewer_h = room["viewer"]
    owner_h = room["owner"][1]

    await async_client.post(
        _comments(pid),
        json=_new_thread(doc, "@viewer please check", mentions=[viewer.id]),
        headers=owner_h,
    )

    [row] = await _bell(async_client, viewer_h)
    assert row["type"] == "comment_mention"
    assert row["payload"]["project_id"] == pid
    assert row["payload"]["document_id"] == doc
    assert row["payload"]["author_name"] == room["owner"][0].display_name
    assert row["payload"]["excerpt"] == "@viewer please check"

    [mail] = _mails(enqueuer)
    assert mail["to"] == viewer.email
    assert mail["context"]["excerpt"] == "@viewer please check"
    assert mail["context"]["comment_url"].endswith(f"?thread={row['payload']['thread_id']}")


async def test_mention_added_by_edit_notifies_once(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    room = await _room(async_client, db_session)
    pid, doc = room["pid"], room["doc"]
    viewer = room["viewer"][0]
    editor_h = room["editor"][1]
    thread = await _start(async_client, pid, editor_h, doc)
    reply = await _reply(async_client, pid, editor_h, thread["id"], "draft")
    url = f"{_comments(pid)}/{thread['id']}/messages/{reply['id']}"

    for body in ("@viewer look", "@viewer look again"):
        response = await async_client.patch(
            url, json={"body": body, "mentions": [str(viewer.id)]}, headers=editor_h
        )
        assert response.status_code == 200, response.text
    assert len(_mails(enqueuer)) == 1
    assert len(await _bell(async_client, room["viewer"][1])) == 1


async def test_reply_notifies_earlier_participants_in_the_bell_only(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    room = await _room(async_client, db_session)
    pid, doc = room["pid"], room["doc"]
    owner_h, editor_h, viewer_h = room["owner"][1], room["editor"][1], room["viewer"][1]
    thread = await _start(async_client, pid, owner_h, doc)

    await _reply(async_client, pid, editor_h, thread["id"], "I agree")
    assert [n["type"] for n in await _bell(async_client, owner_h)] == ["comment_reply"]
    assert await _bell(async_client, editor_h) == []
    assert await _bell(async_client, viewer_h) == []
    assert _mails(enqueuer) == []

    await _reply(async_client, pid, viewer_h, thread["id"], "Me too")
    assert [n["type"] for n in await _bell(async_client, editor_h)] == ["comment_reply"]
    assert len(await _bell(async_client, owner_h)) == 2
    assert await _bell(async_client, viewer_h) == []


async def test_comment_does_not_touch_crdt(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid, doc, owner_h = room["pid"], room["doc"], room["owner"][1]

    before = await db_session.scalar(select(func.count()).select_from(CrdtUpdate))
    thread = await _start(async_client, pid, owner_h, doc)
    await _reply(async_client, pid, owner_h, thread["id"], "one more")
    after = await db_session.scalar(select(func.count()).select_from(CrdtUpdate))
    assert after == before


async def test_event_is_published_after_the_commit(
    async_client: AsyncClient, db_session: AsyncSession, redis: Any
) -> None:
    room = await _room(async_client, db_session)
    pid, doc, owner_h = room["pid"], room["doc"], room["owner"][1]
    pubsub = await subscribe(redis, UUID(pid))

    thread = await _start(async_client, pid, owner_h, doc)
    created = await next_event(pubsub)
    assert created["type"] == "comment.thread_created"
    assert created["payload"]["id"] == thread["id"]

    await _reply(async_client, pid, owner_h, thread["id"], "second")
    assert (await next_event(pubsub))["type"] == "comment.message_created"

    await async_client.post(f"{_comments(pid)}/{thread['id']}/resolve", headers=owner_h)
    resolved = await next_event(pubsub)
    assert resolved["type"] == "comment.thread_resolved"
    assert resolved["payload"]["resolved_at"] is not None


async def test_event_not_published_on_rollback(
    async_client: AsyncClient, db_session: AsyncSession, app: Any, redis: Any
) -> None:
    room = await _room(async_client, db_session)
    pid, doc, owner_h = room["pid"], room["doc"], room["owner"][1]
    pubsub = await subscribe(redis, UUID(pid))
    app.dependency_overrides[get_db_session] = failing_commit_session(db_session)

    response = await async_client.post(_comments(pid), json=_new_thread(doc), headers=owner_h)
    assert response.status_code == 500
    assert await no_event(pubsub)
