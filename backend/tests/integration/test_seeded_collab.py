"""Editing a lived-in project over the collab socket: the seeded text is the base of every edit."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.ws.components import CollabComponents
from inkstave.modules.history.models import HistoryUpdate
from inkstave.modules.projects.models.document import Document
from tests.collab_ws_harness import install_collab
from tests.factories.lived_in import APPENDIX_TEX, MAIN_TEX, LivedInProject
from tests.integration._seeded_support import connect, sync_editor, type_edit

pytestmark = pytest.mark.integration

_SETTLE = 0.05


async def _content(db_session: AsyncSession, doc_id: Any) -> str:
    db_session.expire_all()
    return str(await db_session.scalar(select(Document.content).where(Document.entity_id == doc_id)))


async def _state_at(components: CollabComponents, doc_id: Any, version: int) -> str:
    assert components.history is not None
    return _text(await components.history.reconstruct_state(doc_id=doc_id, version=version))


def _text(state: bytes) -> str:
    doc = YDocument()
    doc.apply_update(state)
    return doc.text


async def test_seeded_older_document_edit_keeps_the_seed_in_history(
    app: Any, db_session: AsyncSession, redis: Any, lived_in_project: LivedInProject
) -> None:
    """The bug of 5548812: a document with no history yet, opened and edited for the first time."""
    components = install_collab(app, db_session, redis, history_debounce_ms=10_000_000)
    doc_id = lived_in_project.ids["appendix.tex"]
    edited = APPENDIX_TEX.replace("Written before history existed.", "Edited by a collaborator.")

    async with connect(app, lived_in_project.project_id, doc_id, lived_in_project.collaborator) as ws:
        local = await sync_editor(ws)
        assert local.text == APPENDIX_TEX  # the seed reached the editor
        await type_edit(ws, local, edited)
        await asyncio.sleep(_SETTLE)
    await asyncio.sleep(_SETTLE)
    await components.manager.flush(doc_id)
    assert await _content(db_session, doc_id) == edited

    assert components.history is not None
    await components.history.flush_doc(doc_id=doc_id, reason="manual")
    assert await _state_at(components, doc_id, 1) == edited


async def test_seeded_versioned_document_continues_its_history(
    app: Any, db_session: AsyncSession, redis: Any, lived_in_project: LivedInProject
) -> None:
    """``main.tex`` has two recorded versions; an edit over the socket adds version 3 on top of them."""
    components = install_collab(app, db_session, redis, history_debounce_ms=10_000_000)
    doc_id = lived_in_project.main_id
    edited = MAIN_TEX + "% added over the socket\n"

    async with connect(app, lived_in_project.project_id, doc_id, lived_in_project.owner) as ws:
        local = await sync_editor(ws)
        assert local.text == MAIN_TEX
        await type_edit(ws, local, edited)
        await asyncio.sleep(_SETTLE)
    await asyncio.sleep(_SETTLE)
    assert components.history is not None
    await components.history.flush_doc(doc_id=doc_id, reason="manual")

    assert await _state_at(components, doc_id, 2) == MAIN_TEX
    assert await _state_at(components, doc_id, 3) == edited
    versions = list(
        await db_session.scalars(
            select(HistoryUpdate.version)
            .where(HistoryUpdate.doc_id == doc_id)
            .order_by(HistoryUpdate.version)
        )
    )
    assert versions == [1, 2, 3]
