"""Shared helpers and fixtures for the history API integration tests (spec 37).

Covers versions, updates, diff, labels and auth. The original single module was
split into cohesive sibling ``test_history_api*.py`` files by concern; the shared
``hist`` fixture, auth/version helpers and URL builder live here.

This module is intentionally not ``test_``-prefixed so pytest does not collect
it. The sibling ``test_history_api*.py`` modules import the fixtures and helpers
they need from here to stay DRY.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import install_collab
from tests.factories import UserFactory

_NOW = datetime(2026, 6, 10, tzinfo=UTC)
API = "/api/v1/projects"


async def _user(db_session: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def _member(db_session: AsyncSession, pid: UUID, user_id: UUID, role: str) -> None:
    db_session.add(
        ProjectMembership(
            project_id=pid, user_id=user_id, role=role, status=MembershipStatus.active
        )
    )
    await db_session.commit()


async def _set_version(comp: Any, pid: UUID, doc_id: UUID, text: str, author_id: UUID) -> None:
    update = await comp.manager.apply_server_update(doc_id, text, "setup")
    await comp.history.capture_update(
        project_id=pid, doc_id=doc_id, update=update, author_id=author_id, at=_NOW
    )
    await comp.history.flush_doc(doc_id=doc_id, reason="manual")


@pytest.fixture
async def hist(app: Any, async_client: AsyncClient, db_session: AsyncSession, redis: Any):
    comp = install_collab(app, db_session, redis, history_debounce_ms=10_000_000)
    owner, owner_h = await _user(db_session)
    project = await create_project(db_session, owner.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "")
    await db_session.commit()

    editor, editor_h = await _user(db_session)
    await _member(db_session, project.id, editor.id, MembershipRole.editor)
    viewer, viewer_h = await _user(db_session)
    await _member(db_session, project.id, viewer.id, MembershipRole.viewer)
    _outsider, outsider_h = await _user(db_session)

    for text in ("line one\n", "line one\nline two\n", "line one\nLINE TWO\n"):
        await _set_version(comp, project.id, entity.id, text, owner.id)

    return SimpleNamespace(
        comp=comp,
        pid=str(project.id),
        doc_id=str(entity.id),
        doc_uuid=entity.id,
        owner_h=owner_h,
        editor_h=editor_h,
        viewer_h=viewer_h,
        outsider_h=outsider_h,
    )


def _hist_url(pid: str, doc_id: str, suffix: str) -> str:
    return f"{API}/{pid}/docs/{doc_id}/history/{suffix}"
