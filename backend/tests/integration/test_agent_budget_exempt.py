"""Integration: a user listed in AGENT_BUDGET_EXEMPT_EMAILS runs past every token and cost cap."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.llm.fake import FakeLLM
from inkstave.modules.agent.runs.events import InMemoryEventSink
from inkstave.modules.agent.runs.jobs import run_agent_turn
from inkstave.modules.agent.safety import record_usage

from .test_agent_safety_api import _NOW, _ctx, _tool_call, seed

pytestmark = pytest.mark.integration

__all__ = ["seed"]


async def _exhaust_day(redis: Any, seed: SimpleNamespace) -> None:
    await record_usage(
        redis, user_id=seed.owner.id, project_id=seed.project.id, now=_NOW, tokens=10, cost=Decimal("1")
    )


async def test_exempt_user_runs_past_the_day_and_run_caps(
    seed: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    settings = AgentSettings(
        agent_max_tokens_per_day_per_project=10,
        agent_max_cost_per_day_per_user_usd=0.30,
        agent_max_tokens_per_run=50,
        agent_budget_exempt_emails=f"someone@else.org, {seed.owner.email.upper()} ",
    )
    await _exhaust_day(redis, seed)
    sink = InMemoryEventSink(str(seed.run_id))
    steps = [_tool_call("read_file", {"doc_id": str(seed.main_id)}, usage=100)] * 2
    llm = FakeLLM(script=[*steps, FakeLLM.respond_text("done")])

    await run_agent_turn(
        _ctx(db_session, redis, llm, sink, settings),
        session_id=str(seed.session.id),
        run_id=str(seed.run_id),
        user_message="x",
    )

    assert len(llm.calls) == 3
    assert all(e.get("code") != "agent_budget_exceeded" for e in sink.events)


async def test_a_user_not_listed_keeps_the_caps(
    seed: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    settings = AgentSettings(
        agent_max_tokens_per_day_per_project=10, agent_budget_exempt_emails="someone@else.org"
    )
    await _exhaust_day(redis, seed)
    sink = InMemoryEventSink(str(seed.run_id))
    llm = FakeLLM(script=[FakeLLM.respond_text("hi")])

    await run_agent_turn(
        _ctx(db_session, redis, llm, sink, settings),
        session_id=str(seed.session.id),
        run_id=str(seed.run_id),
        user_message="x",
    )

    assert sink.events[-1]["code"] == "agent_budget_exceeded"
    assert llm.calls == []
