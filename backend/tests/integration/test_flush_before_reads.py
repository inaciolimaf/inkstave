"""An agent run or a compile sees the text typed just before it (regression).

The browser's unsaved edits reach the server's CRDT room and are flushed to ``documents.content`` by the request
that starts the job, before the job is queued. The worker reads that column, so it must hold the new text. The
debounce is set long enough that only the forced flush can write it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.agent.deps import get_agent_enqueuer
from inkstave.modules.collab import YDocument
from inkstave.modules.compile.deps import get_compile_enqueuer
from inkstave.modules.projects import read_content_for_collab
from tests.collab_ws_harness import install_collab

from ._agent_api_support import API, seed

__all__ = ["seed"]

pytestmark = pytest.mark.integration

OLD_TEXT = "line0\nline1\nline2\n"
TYPED_TEXT = "typed just now\n"


class _RecordingEnqueuer:
    """Stands in for the worker queue: records what ``documents.content`` holds when the job is queued."""

    def __init__(self, db: AsyncSession, main_id: UUID) -> None:
        self._db = db
        self._main_id = main_id
        self.seen: list[str] = []

    async def enqueue(self, *_args: Any, **_kwargs: Any) -> str | None:
        self.seen.append(await read_content_for_collab(self._db, self._main_id))
        return "job"


def _edit_to(open_state: bytes, text: str) -> bytes:
    editor = YDocument()
    editor.apply_update(open_state)
    collected: list[bytes] = []
    editor.observe(lambda update, _origin: collected.append(update))
    editor.replace_text(text)
    return collected[-1]


async def _unflushed_typing(app: Any, db_session: AsyncSession, redis: Any, seed: SimpleNamespace) -> None:
    comps = install_collab(app, db_session, redis, collab_text_flush_debounce_ms=60_000)
    handle = await comps.manager.acquire(seed.main_id)
    await comps.manager.handle_update(
        seed.main_id, _edit_to(handle.ydoc.get_state(), TYPED_TEXT), origin="browser"
    )
    # The edit is in the room only: the column still holds the text from before it.
    assert await read_content_for_collab(db_session, seed.main_id) == OLD_TEXT


async def test_agent_run_is_queued_with_the_text_typed_before_it(
    app: Any,
    db_session: AsyncSession,
    redis: Any,
    async_client: AsyncClient,
    seed: SimpleNamespace,
) -> None:
    await _unflushed_typing(app, db_session, redis, seed)
    enqueuer = _RecordingEnqueuer(db_session, seed.main_id)
    app.dependency_overrides[get_agent_enqueuer] = lambda: enqueuer
    base = f"{API}/{seed.project.id}/agent"
    sid = (await async_client.post(f"{base}/sessions", json={}, headers=seed.headers)).json()["id"]

    posted = await async_client.post(
        f"{base}/sessions/{sid}/messages", json={"content": "rewrite it"}, headers=seed.headers
    )

    assert posted.status_code == 202
    assert enqueuer.seen == [TYPED_TEXT]


async def test_compile_is_queued_with_the_text_typed_before_it(
    app: Any,
    db_session: AsyncSession,
    redis: Any,
    async_client: AsyncClient,
    seed: SimpleNamespace,
) -> None:
    await _unflushed_typing(app, db_session, redis, seed)
    enqueuer = _RecordingEnqueuer(db_session, seed.main_id)
    app.dependency_overrides[get_compile_enqueuer] = lambda: enqueuer

    posted = await async_client.post(f"{API}/{seed.project.id}/compile", json={}, headers=seed.headers)

    assert posted.status_code == 202
    assert enqueuer.seen == [TYPED_TEXT]
