"""view_image: the model sees the picture, and the stored transcript does not keep it."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.graph import repository as agent_repo
from inkstave.modules.agent.graph.agent_deps import AgentDeps
from inkstave.modules.agent.graph.runner import run_turn
from inkstave.modules.agent.llm.fake import FakeLLM
from inkstave.modules.agent.tools import default_registry
from inkstave.modules.agent.tools.files.view_image import ViewImageArgs, ViewImageTool
from inkstave.modules.projects.content import files as file_service
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity

from ._agent_tools_support import _ctx, _session, _tool_call, seed
from ._tree_api_support import InMemoryObjectStore

pytestmark = pytest.mark.integration

__all__ = ["seed"]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _reader(data: bytes) -> Any:
    state = {"pos": 0}

    async def read(size: int = -1) -> bytes:
        chunk = data[state["pos"] :] if size < 0 else data[state["pos"] : state["pos"] + size]
        state["pos"] += len(chunk)
        return chunk

    return read


async def _upload(db: AsyncSession, seed: SimpleNamespace, store: InMemoryObjectStore, name: str) -> None:
    folder = await create_entity(db, seed.project_id, TreeEntityType.folder, "figures", None)
    source = file_service.UploadSource(name, _reader(PNG), "image/png", name)
    await file_service.upload_file(db, store, seed.project_id, folder.id, source)
    await db.flush()


async def test_view_image_returns_the_image_beside_the_result(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    store = InMemoryObjectStore()
    await _upload(db_session, seed, store, "plot.png")
    ctx = _ctx(db_session, seed.project_id, seed.owner.id)
    ctx.object_store = store
    result = await ViewImageTool().run(ViewImageArgs(path="/figures/plot.png"), ctx)
    assert result.ok and result.data is not None
    assert result.data["media_type"] == "image/png" and result.images[0].media_type == "image/png"


async def test_view_image_refuses_what_it_cannot_show(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    store = InMemoryObjectStore()
    await _upload(db_session, seed, store, "plot.png")
    ctx = _ctx(db_session, seed.project_id, seed.owner.id, agent_tool_image_max_bytes=10)
    ctx.object_store = store
    big = await ViewImageTool().run(ViewImageArgs(path="figures/plot.png"), ctx)
    assert big.error is not None and big.error.code == "too_large"
    doc = await ViewImageTool().run(ViewImageArgs(path="main.tex"), ctx)
    assert doc.error is not None and doc.error.code == "not_found"


async def test_the_model_gets_the_image_and_the_transcript_does_not(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    store = InMemoryObjectStore()
    await _upload(db_session, seed, store, "plot.png")
    session = await _session(db_session, seed)
    llm = FakeLLM(script=[_tool_call("view_image", {"path": "figures/plot.png"})])
    deps = AgentDeps(llm=llm, settings=AgentSettings(), tools=default_registry(), object_store=store)
    await run_turn(session=session, user_message="what is this?", deps=deps, db=db_session)

    sent: list[Any] = llm.calls[-1]["messages"]  # type: ignore[assignment]
    assert any(m.images for m in sent if m.role == "tool")
    rows = await agent_repo.list_messages(db_session, session.id)
    stored = next(r for r in rows if r.role == "tool")
    assert "image/png" in (stored.content or "")
    assert "iVBOR" not in (stored.content or "")  # no base64 of the picture
