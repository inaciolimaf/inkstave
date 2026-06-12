"""Integration tests for agent act-node tool execution through the graph (spec 42).

Shared helpers/fixtures live in ``_agent_tools_support.py``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent import repository as agent_repo
from inkstave.agent.deps import AgentDeps
from inkstave.agent.llm.fake import FakeLLM
from inkstave.agent.runner import run_turn
from inkstave.agent.settings import AgentSettings
from inkstave.agent.tools import default_registry
from inkstave.services.document_service import get_document

from ._agent_tools_support import _session, _tool_call, seed

pytestmark = pytest.mark.integration

__all__ = ["seed"]


async def test_act_runs_real_tool_via_graph(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    session = await _session(db_session, seed)
    deps = AgentDeps(
        llm=FakeLLM(script=[_tool_call("search_project", {"query": "introduction"})]),
        settings=AgentSettings(),
        tools=default_registry(),
    )
    await run_turn(session=session, user_message="find intro", deps=deps, db=db_session)
    rows = await agent_repo.list_messages(db_session, session.id)
    tool_rows = [r for r in rows if r.role == "tool"]
    assert tool_rows  # AC8: a real tool produced a role=tool message
    payload = json.loads(tool_rows[0].content or "{}")
    assert payload["ok"] is True and "matches" in payload["data"]


async def test_locate_section_via_graph_is_structure_aware(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    # Spec 48 AC6: the spec-42 locate_section tool, run inside the graph, returns the
    # structure-aware range with the tool contract preserved.
    session = await _session(db_session, seed)
    deps = AgentDeps(
        llm=FakeLLM(script=[_tool_call("locate_section", {"name": "introduction"})]),
        settings=AgentSettings(),
        tools=default_registry(),
    )
    await run_turn(session=session, user_message="where is the intro", deps=deps, db=db_session)
    rows = await agent_repo.list_messages(db_session, session.id)
    payload = json.loads(next(r for r in rows if r.role == "tool").content or "{}")
    assert payload["ok"] is True
    assert payload["data"]["method"] == "structure-v1"
    match = payload["data"]["matches"][0]
    assert match["title"] == "Introduction" and match["heading_line"] == 3


async def test_act_unknown_tool_is_unsupported(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    session = await _session(db_session, seed)
    deps = AgentDeps(
        llm=FakeLLM(script=[_tool_call("ghost", {})]),
        settings=AgentSettings(),
        tools=default_registry(),
    )
    await run_turn(session=session, user_message="x", deps=deps, db=db_session)
    rows = await agent_repo.list_messages(db_session, session.id)
    payload = json.loads(next(r for r in rows if r.role == "tool").content or "{}")
    assert payload["ok"] is False and payload["error"]["code"] == "unsupported"  # AC8


async def test_act_invalid_args_is_invalid_args(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    session = await _session(db_session, seed)
    deps = AgentDeps(
        llm=FakeLLM(script=[_tool_call("read_file", {})]),  # neither selector → invalid
        settings=AgentSettings(),
        tools=default_registry(),
    )
    await run_turn(session=session, user_message="x", deps=deps, db=db_session)
    rows = await agent_repo.list_messages(db_session, session.id)
    payload = json.loads(next(r for r in rows if r.role == "tool").content or "{}")
    assert payload["ok"] is False and payload["error"]["code"] == "invalid_args"  # AC9


async def test_propose_edit_via_graph_stages_and_keeps_doc(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    session = await _session(db_session, seed)
    before = (await get_document(db_session, seed.project_id, seed.main_id)).content
    deps = AgentDeps(
        llm=FakeLLM(
            script=[
                _tool_call(
                    "propose_edit",
                    {"doc_id": str(seed.main_id), "mode": "full", "new_text": "brand new"},
                )
            ]
        ),
        settings=AgentSettings(),
        tools=default_registry(),
    )
    result = await run_turn(session=session, user_message="rewrite", deps=deps, db=db_session)
    assert len(result.staged_edits) == 1  # AC5 via graph
    after = (await get_document(db_session, seed.project_id, seed.main_id)).content
    assert after == before  # document untouched
