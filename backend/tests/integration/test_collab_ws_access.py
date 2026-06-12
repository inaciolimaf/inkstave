"""Spec-34 access control on the collaboration WebSocket (viewer read-only, etc.)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.collab.ydocument import YDocument
from inkstave.config import get_settings
from inkstave.db.models.crdt import CrdtUpdate
from inkstave.db.models.document import Document
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import (
    ASGIWebSocketClient,
    apply_update_message,
    install_collab,
    make_update,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


def _token(user: Any) -> str:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return token


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
            "editor": _token(editor),
            "viewer": _token(viewer),
            "outsider": _token(outsider),
        },
    )


def _path(project_id: Any, document_id: Any) -> str:
    return f"/ws/collab/projects/{project_id}/documents/{document_id}"


async def test_non_member_join_rejected_4403(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis)
    project, entity, tokens = await _setup(db_session)
    async with ASGIWebSocketClient(
        app, _path(project.id, entity.id), query=f"token={tokens['outsider']}"
    ) as ws:
        assert await ws.close_code() == 4403  # AC6 — no room, no sync


async def test_viewer_update_is_dropped(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    project, entity, tokens = await _setup(db_session)
    path = _path(project.id, entity.id)
    # A second client (an editor on the same doc) joins so we can prove the
    # dropped viewer update is not broadcast to anyone (AC7), not merely unpersisted.
    async with (
        ASGIWebSocketClient(app, path, query=f"token={tokens['viewer']}") as v,
        ASGIWebSocketClient(app, path, query=f"token={tokens['editor']}") as e,
    ):
        await v.expect_accept()  # viewer DOES join (read access)
        await v.receive_bytes()  # server step1
        await e.expect_accept()
        await e.receive_bytes()  # server step1

        await v.send_bytes(make_update("sneaky viewer edit"))
        await asyncio.sleep(0.05)

        # AC7: the viewer's update is dropped — the editor client receives no relay.
        await e.expect_no_message()

    # AC7: nothing applied or persisted from the viewer.
    count = await db_session.scalar(
        select(func.count()).select_from(CrdtUpdate).where(CrdtUpdate.document_id == entity.id)
    )
    assert count == 0


async def test_viewer_receives_editor_updates(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis)
    project, entity, tokens = await _setup(db_session)
    path = _path(project.id, entity.id)
    async with (
        ASGIWebSocketClient(app, path, query=f"token={tokens['viewer']}") as v,
        ASGIWebSocketClient(app, path, query=f"token={tokens['editor']}") as e,
    ):
        await v.expect_accept()
        await v.receive_bytes()  # server step1
        await e.expect_accept()
        await e.receive_bytes()

        await e.send_bytes(make_update("editor edit"))
        relayed = await v.receive_bytes()  # viewer still sees others' edits (AC7)
        local = YDocument()
        apply_update_message(local, relayed)
        assert local.text == "editor edit"


async def test_editor_update_applies_and_persists(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    components = install_collab(app, db_session, redis)
    project, entity, tokens = await _setup(db_session)
    async with ASGIWebSocketClient(
        app, _path(project.id, entity.id), query=f"token={tokens['editor']}"
    ) as e:
        await e.expect_accept()
        await e.receive_bytes()
        await e.send_bytes(make_update("editor wrote this"))
        await asyncio.sleep(0.05)

        count = await db_session.scalar(
            select(func.count()).select_from(CrdtUpdate).where(CrdtUpdate.document_id == entity.id)
        )
        assert count >= 1  # AC8 applied + persisted

        await components.manager.flush(entity.id)
        content = await db_session.scalar(
            select(Document.content).where(Document.entity_id == entity.id)
        )
        assert content == "editor wrote this"
