"""Integration tests for history restore (spec 37): non-destructive, broadcast, atomic."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.history import HistoryLabel, HistoryUpdate
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import install_collab
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 10, tzinfo=UTC)
API = "/api/v1/projects"


async def _user(db_session: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def _set_version(comp: Any, pid: UUID, doc_id: UUID, text: str, author_id: UUID) -> None:
    update = await comp.manager.apply_server_update(doc_id, text, "setup")
    await comp.history.capture_update(
        project_id=pid, doc_id=doc_id, update=update, author_id=author_id, at=_NOW
    )
    await comp.history.flush_doc(doc_id=doc_id, reason="manual")


async def _max_version(db_session: AsyncSession, doc_id: UUID) -> int:
    value = await db_session.scalar(
        select(func.max(HistoryUpdate.version)).where(HistoryUpdate.doc_id == doc_id)
    )
    return int(value) if value is not None else 0


@pytest.fixture
async def hist(app: Any, async_client: AsyncClient, db_session: AsyncSession, redis: Any):
    comp = install_collab(app, db_session, redis, history_debounce_ms=10_000_000)
    owner, owner_h = await _user(db_session)
    project = await create_project(db_session, owner.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "")
    await db_session.commit()
    editor, editor_h = await _user(db_session)
    db_session.add(
        ProjectMembership(
            project_id=project.id,
            user_id=editor.id,
            role=MembershipRole.editor,
            status=MembershipStatus.active,
        )
    )
    await db_session.commit()
    for text in ("alpha\n", "alpha\nbeta\n", "alpha\nGAMMA\n"):
        await _set_version(comp, project.id, entity.id, text, owner.id)
    return SimpleNamespace(
        comp=comp,
        pid=str(project.id),
        pid_uuid=project.id,
        doc_id=str(entity.id),
        doc_uuid=entity.id,
        owner_h=owner_h,
        editor_h=editor_h,
    )


def _url(pid: str, doc_id: str, suffix: str) -> str:
    return f"{API}/{pid}/docs/{doc_id}/history/{suffix}"


async def test_restore_creates_new_version_non_destructive(
    hist: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    published: list[Any] = []

    async def fake_publish(*args: Any, **kwargs: Any) -> None:
        published.append(args)

    monkeypatch.setattr(hist.comp.redis_bridge, "publish", fake_publish)

    r = await async_client.post(
        _url(hist.pid, hist.doc_id, "restore"), json={"version": 1}, headers=hist.editor_h
    )
    assert r.status_code == 200
    body = r.json()
    assert body["restored_from_version"] == 1
    assert body["new_version"] == 4  # AC6a: a NEW version above current(3)
    assert published  # AC6d: broadcast hook invoked

    # AC6c: all prior versions still exist (nothing destroyed).
    versions = (
        await async_client.get(_url(hist.pid, hist.doc_id, "versions"), headers=hist.editor_h)
    ).json()["versions"]
    assert {v["version"] for v in versions} >= {1, 2, 3, 4}

    # AC6b: the live text now equals version 1 — diff(v1, current) is empty.
    diff = (
        await async_client.get(
            _url(hist.pid, hist.doc_id, "diff?from=1&to=current"), headers=hist.editor_h
        )
    ).json()
    changed = [s for h in diff["hunks"] for s in h["segments"] if s["type"] != "context"]
    assert changed == []


async def test_restore_label_attaches_to_new_version(
    hist: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    r = await async_client.post(
        _url(hist.pid, hist.doc_id, "restore"),
        json={"version": 1, "label_name": "rolled back"},
        headers=hist.editor_h,
    )
    body = r.json()
    assert body["label"]["name"] == "rolled back"
    assert body["label"]["version"] == body["new_version"]  # AC7: on N, not on 1


async def test_restore_atomic_on_room_failure(
    hist: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession, monkeypatch: Any
) -> None:
    async def boom(*args: Any, **kwargs: Any) -> bytes:
        raise RuntimeError("room unreachable")

    monkeypatch.setattr(hist.comp.manager, "apply_server_update", boom)
    before = await _max_version(db_session, hist.doc_uuid)

    r = await async_client.post(
        _url(hist.pid, hist.doc_id, "restore"),
        json={"version": 1, "label_name": "should-not-exist"},
        headers=hist.editor_h,
    )
    assert r.status_code == 409  # AC12
    assert await _max_version(db_session, hist.doc_uuid) == before  # no new version
    label = await db_session.scalar(
        select(HistoryLabel).where(HistoryLabel.name == "should-not-exist")
    )
    assert label is None  # no label created


async def test_project_restore_per_doc_results(
    hist: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # A project-level label captures {doc: current_version}.
    label = await async_client.post(
        f"{API}/{hist.pid}/history/labels", json={"name": "checkpoint"}, headers=hist.owner_h
    )
    assert label.status_code == 201
    label_id = label.json()["id"]

    # Move the doc forward, then restore the whole project to the checkpoint.
    await _set_version(hist.comp, hist.pid_uuid, hist.doc_uuid, "alpha\nGAMMA\ndelta\n", None)

    r = await async_client.post(
        f"{API}/{hist.pid}/history/restore", json={"label_id": label_id}, headers=hist.editor_h
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1  # the one doc with history
    assert results[0]["status"] == "restored" and results[0]["new_version"] is not None  # AC9
