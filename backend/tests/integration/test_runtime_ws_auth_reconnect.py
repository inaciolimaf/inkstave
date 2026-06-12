"""Spec 65: runtime-safety tests for the collab WebSocket — auth, reconnect,
viewer read-only. In-process ASGI client + fake Redis + transactional DB only;
no real network, Redis, or browser. Observes existing behaviour — no prod change.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.collab.protocol import (
    SyncStep2,
    SyncUpdate,
    encode_sync_step1,
    encode_update,
    read_message,
)
from inkstave.collab.ydocument import YDocument
from inkstave.config import Settings, get_settings
from inkstave.db.models.crdt import CrdtUpdate
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import ASGIWebSocketClient, install_collab, make_update
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404


def _token(user: Any) -> str:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return token


def _path(project_id: Any, document_id: Any) -> str:
    return f"/ws/collab/projects/{project_id}/documents/{document_id}"


async def _setup(db_session: AsyncSession):
    owner = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, owner.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    editor = await UserFactory.create(db_session)
    viewer = await UserFactory.create(db_session)
    outsider = await UserFactory.create(db_session)
    await db_session.flush()
    for user, role in ((editor, MembershipRole.editor), (viewer, MembershipRole.viewer)):
        db_session.add(
            ProjectMembership(
                project_id=project.id,
                user_id=user.id,
                role=role,
                status=MembershipStatus.active,
            )
        )
    await db_session.flush()
    return (
        project,
        entity,
        {
            "owner": _token(owner),
            "editor": _token(editor),
            "viewer": _token(viewer),
            "outsider": _token(outsider),
        },
    )


def _apply_sync(doc: YDocument, data: bytes) -> bool:
    """Apply a SyncStep2/SyncUpdate frame into ``doc``; return True if applied."""
    parsed = read_message(data)
    if isinstance(parsed, (SyncStep2, SyncUpdate)):
        doc.apply_update(parsed.update)
        return True
    return False


async def _handshake_and_sync(ws: ASGIWebSocketClient) -> YDocument:
    """Complete the client side of the handshake; return a local doc synced to the
    server's full state (request it via a SyncStep1 with an empty state vector)."""
    await ws.expect_accept()
    await ws.receive_bytes()  # server's initial SyncStep1
    local = YDocument()
    await ws.send_bytes(encode_sync_step1(local.get_state_vector()))
    _apply_sync(local, await ws.receive_bytes())  # server's SyncStep2 (full state)
    # The server enqueues its SyncStep1 exactly once, at connect (consumed above);
    # it deliberately suppresses the duplicate when answering the client's
    # SyncStep1, so there is no trailing SyncStep1 to drain here.
    return local


# --- AC1–AC4: auth rejection before accept, no room, no manager acquire ------ #


async def test_missing_token_rejected_4401_no_room(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    components = install_collab(app, db_session, redis)
    project, entity, _ = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, entity.id)) as ws:  # no ?token=
        assert await ws.close_code() == CLOSE_UNAUTHORIZED  # AC1
    assert components.rooms.room_count() == 0  # AC4
    assert entity.id not in components.manager.load_count  # AC4 — never acquired


async def test_malformed_token_rejected_4401(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    components = install_collab(app, db_session, redis)
    project, entity, _ = await _setup(db_session)
    async with ASGIWebSocketClient(
        app, _path(project.id, entity.id), query="token=not-a-jwt"
    ) as ws:
        assert await ws.close_code() == CLOSE_UNAUTHORIZED  # AC2
    assert components.rooms.room_count() == 0
    assert entity.id not in components.manager.load_count


async def test_expired_token_rejected_4401(app: Any, db_session: AsyncSession, redis: Any) -> None:
    components = install_collab(app, db_session, redis)
    project, entity, _ = await _setup(db_session)
    user = await UserFactory.create(db_session)
    db_session.add(
        ProjectMembership(
            project_id=project.id,
            user_id=user.id,
            role=MembershipRole.editor,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()
    # Sign with the app's real secret but an already-elapsed TTL so the claim's
    # `exp` is in the past — the server decode rejects it via TokenError → 4401.
    expired_service = build_token_service(
        Settings(_env_file=None, access_token_ttl_seconds=-1)  # type: ignore[call-arg]
    )
    expired_token, _ = expired_service.create_access_token(user)
    async with ASGIWebSocketClient(
        app, _path(project.id, entity.id), query=f"token={expired_token}"
    ) as ws:
        assert await ws.close_code() == CLOSE_UNAUTHORIZED  # AC3 (expiry enforced)
    assert components.rooms.room_count() == 0
    assert entity.id not in components.manager.load_count


async def test_non_member_4403_and_unknown_4404(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis)
    project, entity, tokens = await _setup(db_session)
    # Authenticated non-member of an existing project/doc → 4403.
    async with ASGIWebSocketClient(
        app, _path(project.id, entity.id), query=f"token={tokens['outsider']}"
    ) as ws:
        assert await ws.close_code() == CLOSE_FORBIDDEN  # AC5
    # Valid token, unknown project/doc ids → 4404.
    async with ASGIWebSocketClient(
        app, _path(uuid4(), uuid4()), query=f"token={tokens['editor']}"
    ) as ws:
        assert await ws.close_code() == CLOSE_NOT_FOUND  # AC5


# --- AC6/AC7: reconnect re-sync, lossless + convergent ----------------------- #


async def test_reconnect_resyncs_seeded_text_losslessly(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis)
    project, entity, tokens = await _setup(db_session)
    await set_content_from_collab(db_session, entity.id, "alpha")
    await db_session.flush()
    path = _path(project.id, entity.id)

    # First connection joins, then drops.
    async with ASGIWebSocketClient(app, path, query=f"token={tokens['editor']}") as e1:
        local = await _handshake_and_sync(e1)
        assert local.text == "alpha"

    # A fresh connection by the same user re-syncs the full text — no loss/dup.
    async with ASGIWebSocketClient(app, path, query=f"token={tokens['editor']}") as e2:
        resynced = await _handshake_and_sync(e2)
    assert resynced.text == "alpha"  # AC6
    assert len(resynced.text) == len("alpha")


async def test_two_editors_converge_after_drop(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis)
    project, entity, tokens = await _setup(db_session)
    path = _path(project.id, entity.id)

    a = ASGIWebSocketClient(app, path, query=f"token={tokens['editor']}")
    b = ASGIWebSocketClient(app, path, query=f"token={tokens['owner']}")
    await a.__aenter__()
    await b.__aenter__()
    local_b = YDocument()
    try:
        await _handshake_and_sync(a)
        await _handshake_and_sync(b)
        # A writes "X"; B's live relay proves the server applied it before A drops.
        await a.send_bytes(make_update("X"))
        _apply_sync(local_b, await b.receive_bytes())
        assert local_b.text == "X"
    finally:
        await a.__aexit__()  # A disconnects (B still present → no compaction yet)

    try:
        # B appends "Y" on top of the converged "X".
        update = local_b.replace_text("XY")
        await b.send_bytes(encode_update(update))
        await b.expect_no_message(0.05)  # let the server apply it (B is the sole writer)
    finally:
        await b.__aexit__()  # room empties → state snapshotted as "XY"

    # A reconnects and re-syncs: both edits present, each exactly once.
    async with ASGIWebSocketClient(app, path, query=f"token={tokens['editor']}") as a2:
        resynced = await _handshake_and_sync(a2)
    assert "X" in resynced.text and "Y" in resynced.text  # AC7
    assert resynced.text.count("X") == 1
    assert resynced.text.count("Y") == 1


# --- AC8: viewer read-only (drops writes, still reads) ----------------------- #


async def test_viewer_write_dropped_but_reads(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis)
    project, entity, tokens = await _setup(db_session)
    path = _path(project.id, entity.id)

    async def _count() -> int:
        return await db_session.scalar(  # type: ignore[return-value]
            select(func.count()).select_from(CrdtUpdate).where(CrdtUpdate.document_id == entity.id)
        )

    v = ASGIWebSocketClient(app, path, query=f"token={tokens['viewer']}")
    e = ASGIWebSocketClient(app, path, query=f"token={tokens['editor']}")
    await v.__aenter__()
    await e.__aenter__()
    try:
        await v.expect_accept()
        await v.receive_bytes()  # server step1
        await e.expect_accept()
        await e.receive_bytes()

        # The viewer's write is dropped: never applied, persisted, or broadcast.
        await v.send_bytes(make_update("sneaky viewer edit"))
        await v.expect_no_message(0.1)  # no echo/broadcast back to the viewer
        assert await _count() == 0  # AC8 — nothing persisted from the viewer

        # An editor write IS applied/persisted and relayed to the viewer.
        await e.send_bytes(make_update("editor edit"))
        relayed = YDocument()
        assert _apply_sync(relayed, await v.receive_bytes())  # AC8 — viewer still reads
        assert relayed.text == "editor edit"
        # Exactly one row now exists (the editor's), confirming the viewer's drop
        # was the reason the count was 0 a moment ago — not a broken persist path.
        assert await _count() == 1
    finally:
        await e.__aexit__()
        await v.__aexit__()
