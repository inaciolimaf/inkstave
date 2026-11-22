"""Integration: with the default settings, the per-run token and cost caps stop a turn (spec 49)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.llm.base import LLMResponse, LLMUsage, ToolCall
from inkstave.modules.agent.llm.fake import FakeLLM
from inkstave.modules.agent.runs.events import InMemoryEventSink
from inkstave.modules.agent.runs.jobs import run_agent_turn

from .test_agent_safety_api import _ctx, _tool_call, seed

pytestmark = pytest.mark.integration

__all__ = ["seed"]


def _read_step(seed: SimpleNamespace, usage: LLMUsage) -> LLMResponse:
    call = ToolCall(id=uuid4().hex, name="read_file", arguments={"doc_id": str(seed.main_id)})
    return LLMResponse(tool_calls=[call], usage=usage, finish_reason="tool_calls")


async def test_default_per_run_token_cap_stops_the_turn(
    seed: SimpleNamespace, db_session: AsyncSession, redis: object
) -> None:
    settings = AgentSettings()  # defaults, no test overrides
    sink = InMemoryEventSink(str(seed.run_id))
    step = _tool_call("read_file", {"doc_id": str(seed.main_id)}, usage=300_000)
    llm = FakeLLM(script=[step, step, FakeLLM.respond_text("done")])

    await run_agent_turn(
        _ctx(db_session, redis, llm, sink, settings),
        session_id=str(seed.session.id),
        run_id=str(seed.run_id),
        user_message="x",
    )

    assert sink.events[-1]["code"] == "agent_budget_exceeded"
    assert len(llm.calls) == 2  # the step that would cross the cap never ran


async def test_default_per_run_cost_cap_stops_the_turn(
    seed: SimpleNamespace, db_session: AsyncSession, redis: object
) -> None:
    settings = AgentSettings()  # defaults, no test overrides
    sink = InMemoryEventSink(str(seed.run_id))
    # Output-heavy step: 110k tokens, but ~0.05 USD at the default Haiku rates.
    step = _read_step(seed, LLMUsage(prompt=10_000, completion=100_000, total=110_000))
    llm = FakeLLM(script=[step, step, FakeLLM.respond_text("done")])

    await run_agent_turn(
        _ctx(db_session, redis, llm, sink, settings),
        session_id=str(seed.session.id),
        run_id=str(seed.run_id),
        user_message="x",
    )

    assert sink.events[-1]["code"] == "agent_budget_exceeded"
    assert len(llm.calls) == 1
