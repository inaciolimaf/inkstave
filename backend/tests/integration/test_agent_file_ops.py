"""The agent's file proposals: staging never touches the tree; only the user's apply does."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.core.config.settings import get_settings
from inkstave.infra.deps import get_object_store
from inkstave.modules.agent.file_ops import repo
from inkstave.modules.agent.graph.agent_deps import AgentDeps
from inkstave.modules.agent.graph.runner import run_turn
from inkstave.modules.agent.llm.fake import FakeLLM
from inkstave.modules.agent.tools import default_registry
from inkstave.modules.agent.tools.files.propose import (
    ProposeCreateArgs,
    ProposeCreateTool,
    ProposeDeleteArgs,
    ProposeDeleteTool,
    ProposeMoveArgs,
    ProposeMoveTool,
)
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.projects.content.documents import get_document
from inkstave.modules.projects.models.membership import MembershipRole
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import compute_path, create_entity, get_tree
from tests.factories import UserFactory
from tests.integration._agent_api_support import API, _make_session, _tool_call, seed
from tests.integration._agent_tools_support import _ctx, _member
from tests.integration._tree_api_support import InMemoryObjectStore

pytestmark = pytest.mark.integration

__all__ = ["seed"]


@pytest.fixture
def store(app: Any) -> Iterator[InMemoryObjectStore]:
    memory = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: memory
    yield memory
    app.dependency_overrides.pop(get_object_store, None)


async def _paths(db: AsyncSession, project_id: Any) -> set[str]:
    entities = await get_tree(db, project_id)
    by_id = {e.id: e for e in entities}
    return {compute_path(e, by_id) for e in entities if not e.is_root}


async def _turn(db: AsyncSession, seed: SimpleNamespace, *calls: tuple[str, dict[str, Any]]) -> Any:
    session = await _make_session(db, seed)
    deps = AgentDeps(
        llm=FakeLLM(script=[_tool_call(name, args) for name, args in calls]),
        settings=AgentSettings(),
        tools=default_registry(),
    )
    result = await run_turn(session=session, user_message="go", deps=deps, db=db)
    await db.commit()
    return session, result


def _bearer(user: Any) -> dict[str, str]:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _url(seed: SimpleNamespace, session: Any, op: Any = None, action: str = "") -> str:
    base = f"{API}/{seed.project.id}/agent/sessions/{session.id}/file-ops"
    return f"{base}/{op.id}/{action}" if op is not None else base


async def test_a_proposal_changes_nothing_until_the_user_applies(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient, store: InMemoryObjectStore
) -> None:
    session, result = await _turn(
        db_session,
        seed,
        ("propose_create", {"path": "chapters/one/intro.tex", "content": "Hello\n"}),
        ("propose_delete", {"path": "main.tex"}),
    )
    assert [op.kind for op in result.proposed_file_ops] == ["create", "delete"]
    assert await _paths(db_session, seed.project.id) == {"main.tex"}

    create, delete = result.proposed_file_ops
    response = await async_client.post(_url(seed, session, create, "apply"), headers=seed.headers)
    assert response.status_code == 200 and response.json()["status"] == "applied"
    paths = await _paths(db_session, seed.project.id)
    assert {"chapters", "chapters/one", "chapters/one/intro.tex"} < paths
    document = await get_document(db_session, seed.project.id, create.entity_id)
    assert document.content == "Hello\n"

    response = await async_client.post(_url(seed, session, delete, "reject"), headers=seed.headers)
    assert response.json()["status"] == "rejected"
    assert "main.tex" in await _paths(db_session, seed.project.id)


async def test_delete_and_move_apply_and_cannot_apply_twice(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient, store: InMemoryObjectStore
) -> None:
    folder = await create_entity(db_session, seed.project.id, TreeEntityType.folder, "old", None)
    await create_entity(db_session, seed.project.id, TreeEntityType.doc, "a.tex", folder.id)
    await db_session.commit()
    session, result = await _turn(
        db_session,
        seed,
        ("propose_move", {"path": "main.tex", "new_path": "src/paper.tex"}),
        ("propose_delete", {"path": "/old/"}),
    )
    move, delete = result.proposed_file_ops
    assert delete.affected_paths == ["old", "old/a.tex"]

    for op in (move, delete):
        response = await async_client.post(_url(seed, session, op, "apply"), headers=seed.headers)
        assert response.status_code == 200
    assert await _paths(db_session, seed.project.id) == {"src", "src/paper.tex"}

    again = await async_client.post(_url(seed, session, move, "apply"), headers=seed.headers)
    assert again.status_code == 409 and again.json()["error"]["type"] == "file_op_closed"


async def test_delete_is_refused_when_the_folder_gained_a_file(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient, store: InMemoryObjectStore
) -> None:
    folder = await create_entity(db_session, seed.project.id, TreeEntityType.folder, "old", None)
    await db_session.commit()
    folder_id, project_id = folder.id, seed.project.id
    session, result = await _turn(db_session, seed, ("propose_delete", {"path": "old"}))
    url = _url(seed, session, result.proposed_file_ops[0], "apply")
    await create_entity(db_session, project_id, TreeEntityType.doc, "new.tex", folder_id)
    await db_session.commit()

    response = await async_client.post(url, headers=seed.headers)
    assert response.status_code == 409 and response.json()["error"]["type"] == "file_op_stale"
    assert "old/new.tex" in await _paths(db_session, project_id)


async def test_a_viewer_cannot_apply(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient, store: InMemoryObjectStore
) -> None:
    session, result = await _turn(db_session, seed, ("propose_delete", {"path": "main.tex"}))
    url = _url(seed, session, result.proposed_file_ops[0], "apply")
    project_id = seed.project.id
    session.user_id = (viewer := await UserFactory.create(db_session)).id
    await _member(db_session, project_id, viewer.id, MembershipRole.viewer)
    headers = _bearer(viewer)
    await db_session.commit()

    response = await async_client.post(url, headers=headers)
    assert response.status_code == 403 and response.json()["error"]["type"] == "file_op_forbidden"
    assert "main.tex" in await _paths(db_session, project_id)


async def test_a_later_proposal_replaces_the_open_one_and_lists_carry_content(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient, store: InMemoryObjectStore
) -> None:
    session, _first = await _turn(db_session, seed, ("propose_create", {"path": "a.tex", "content": "1"}))
    deps = AgentDeps(
        llm=FakeLLM(script=[_tool_call("propose_create", {"path": "a.tex", "content": "2"})]),
        settings=AgentSettings(),
        tools=default_registry(),
    )
    await run_turn(session=session, user_message="again", deps=deps, db=db_session)
    await db_session.commit()

    listed = (await async_client.get(_url(seed, session), headers=seed.headers)).json()
    assert [op["content"] for op in listed] == ["2"]
    detail = await async_client.get(
        f"{API}/{seed.project.id}/agent/sessions/{session.id}", headers=seed.headers
    )
    assert [op["content"] for op in detail.json()["file_ops"]] == [None]


async def test_an_outsider_cannot_reach_the_routes(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient, store: InMemoryObjectStore
) -> None:
    session, _result = await _turn(db_session, seed, ("propose_delete", {"path": "main.tex"}))
    outsider = await UserFactory.create(db_session)
    await db_session.commit()
    response = await async_client.get(_url(seed, session), headers=_bearer(outsider))
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("args", "code"),
    [
        ({"path": "main.tex"}, "invalid_args"),
        ({"path": "MAIN.TEX"}, "invalid_args"),
        ({"path": "main.tex/inner.tex"}, "invalid_args"),
        ({"path": "/"}, "invalid_args"),
        ({"path": "a/../b.tex"}, "invalid_args"),
    ],
)
async def test_create_refuses_a_place_that_cannot_hold_it(
    seed: SimpleNamespace, db_session: AsyncSession, args: dict[str, str], code: str
) -> None:
    ctx = _ctx(db_session, seed.project.id, seed.owner.id)
    result = await ProposeCreateTool().run(ProposeCreateArgs(**args), ctx)
    assert not result.ok and result.error is not None and result.error.code == code
    assert ctx.staged_file_ops == []


async def test_move_and_delete_refuse_what_cannot_happen(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    await create_entity(db_session, seed.project.id, TreeEntityType.folder, "dir", None)
    ctx = _ctx(db_session, seed.project.id, seed.owner.id)
    tool = ProposeMoveTool()
    for path, new_path in (("dir", "dir/inner"), ("main.tex", "dir"), ("main.tex", "main.tex"), ("x", "y")):
        result = await tool.run(ProposeMoveArgs(path=path, new_path=new_path), ctx)
        assert not result.ok, (path, new_path)
    missing = await ProposeDeleteTool().run(ProposeDeleteArgs(path="nope"), ctx)
    assert missing.error is not None and missing.error.code == "not_found"

    renamed = await tool.run(ProposeMoveArgs(path="main.tex", new_path="Main.tex"), ctx)
    assert renamed.ok  # only the case changes, so the name it collides with is its own


async def test_one_turn_cannot_propose_two_changes_to_one_path(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    ctx = _ctx(db_session, seed.project.id, seed.owner.id)
    assert (await ProposeDeleteTool().run(ProposeDeleteArgs(path="main.tex"), ctx)).ok
    second = await ProposeMoveTool().run(ProposeMoveArgs(path="main.tex", new_path="b.tex"), ctx)
    assert not second.ok


async def test_viewers_cannot_propose(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    viewer = await UserFactory.create(db_session)
    await _member(db_session, seed.project.id, viewer.id, MembershipRole.viewer)
    ctx = _ctx(db_session, seed.project.id, viewer.id)
    result = await ProposeCreateTool().run(ProposeCreateArgs(path="a.tex"), ctx)
    assert result.error is not None and result.error.code == "forbidden"


async def test_nothing_is_listed_for_a_session_without_proposals(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    session = await _make_session(db_session, seed)
    assert await repo.list_for_session(db_session, session.id) == []
