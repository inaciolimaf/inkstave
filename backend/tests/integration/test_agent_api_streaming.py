"""Integration tests for run_agent_turn streaming events (spec 44)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent.api.events import InMemoryEventSink, request_cancel
from inkstave.agent.api.jobs import run_agent_turn
from inkstave.agent.diffs import repository as diff_repo
from inkstave.agent.llm.fake import FakeLLM
from inkstave.agent.models import AgentSession

from ._agent_api_support import API, _job_ctx, _make_session, _tool_call, seed

__all__ = ["seed"]

pytestmark = pytest.mark.integration


# --- job: streaming events ------------------------------------------------- #


async def test_token_stream_and_done(
    seed: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    session = await _make_session(db_session, seed)
    run_id = str(session.active_run_id)
    sink = InMemoryEventSink(run_id)
    llm = FakeLLM(script=[FakeLLM.respond_text("Hello world", prompt=2, completion=3)])

    await run_agent_turn(
        _job_ctx(db_session, redis, llm, sink),
        session_id=str(session.id),
        run_id=run_id,
        user_message="hi",
    )

    types = [e["type"] for e in sink.events]
    tokens = "".join(e["text"] for e in sink.events if e["type"] == "token")
    assert tokens == "Hello world"  # AC3
    assert types[-1] == "done"
    done = sink.events[-1]
    assert done["final_text"] == "Hello world" and done["usage"]["total"] == 5
    assert all(t != "done" for t in types[:-1])  # terminal is last

    refreshed = await db_session.get(AgentSession, session.id)
    assert refreshed.run_state == "done" and refreshed.active_run_id is None


async def test_tool_call_and_result_events(
    seed: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    session = await _make_session(db_session, seed)
    run_id = str(session.active_run_id)
    sink = InMemoryEventSink(run_id)
    llm = FakeLLM(script=[_tool_call("read_file", {"doc_id": str(seed.main_id)})])

    await run_agent_turn(
        _job_ctx(db_session, redis, llm, sink),
        session_id=str(session.id),
        run_id=run_id,
        user_message="read it",
    )

    call = next(e for e in sink.events if e["type"] == "tool_call")
    result = next(e for e in sink.events if e["type"] == "tool_result")
    assert call["name"] == "read_file"  # AC4
    assert result["tool_call_id"] == call["tool_call_id"] and result["ok"] is True
    assert sink.events[-1]["type"] == "done"


async def test_diff_proposed_event_and_listing(
    seed: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession, redis: Any
) -> None:
    session = await _make_session(db_session, seed)
    run_id = str(session.active_run_id)
    sink = InMemoryEventSink(run_id)
    llm = FakeLLM(
        script=[
            _tool_call(
                "propose_edit",
                {"doc_id": str(seed.main_id), "mode": "full", "new_text": "rewritten\n"},
            )
        ]
    )

    await run_agent_turn(
        _job_ctx(db_session, redis, llm, sink),
        session_id=str(session.id),
        run_id=run_id,
        user_message="rewrite",
    )

    event = next(e for e in sink.events if e["type"] == "diff_proposed")  # AC5
    row = await diff_repo.get(db_session, UUID(event["diff_id"]))
    assert row is not None and str(row.doc_id) == str(seed.main_id)

    listed = await async_client.get(
        f"{API}/{seed.project.id}/agent/sessions/{session.id}/diffs", headers=seed.headers
    )
    assert any(d["id"] == event["diff_id"] for d in listed.json())


async def test_cancellation(seed: SimpleNamespace, db_session: AsyncSession, redis: Any) -> None:
    session = await _make_session(db_session, seed)
    run_id = str(session.active_run_id)
    sink = InMemoryEventSink(run_id)
    await request_cancel(redis, run_id, ttl_seconds=60)  # cancel before the run starts
    llm = FakeLLM(script=[FakeLLM.respond_text("should not finish")])

    await run_agent_turn(
        _job_ctx(db_session, redis, llm, sink),
        session_id=str(session.id),
        run_id=run_id,
        user_message="hi",
    )

    error = sink.events[-1]
    assert error["type"] == "error" and error["code"] == "cancelled"  # AC6
    refreshed = await db_session.get(AgentSession, session.id)
    assert refreshed.run_state == "error" and refreshed.active_run_id is None


async def test_internal_error_emits_single_error(
    seed: SimpleNamespace, db_session: AsyncSession, redis: Any, monkeypatch: Any
) -> None:
    session = await _make_session(db_session, seed)
    run_id = str(session.active_run_id)
    sink = InMemoryEventSink(run_id)

    async def boom(**_kwargs: Any) -> Any:
        raise RuntimeError("kaboom")

    monkeypatch.setattr("inkstave.agent.api.jobs.run_turn", boom)
    llm = FakeLLM(script=[FakeLLM.respond_text("x")])

    # Must NOT raise — the worker survives (AC7).
    await run_agent_turn(
        _job_ctx(db_session, redis, llm, sink),
        session_id=str(session.id),
        run_id=run_id,
        user_message="hi",
    )

    errors = [e for e in sink.events if e["type"] == "error"]
    assert len(errors) == 1 and errors[0]["code"] == "internal"
    refreshed = await db_session.get(AgentSession, session.id)
    assert refreshed.run_state == "error"
