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
    step = _tool_call("read_file", {"doc_id": str(seed.main_id)}, usage=400_000)
    llm = FakeLLM(script=[step, step, step, step, FakeLLM.respond_text("done")])

    await run_agent_turn(
        _ctx(db_session, redis, llm, sink, settings),
        session_id=str(seed.session.id),
        run_id=str(seed.run_id),
        user_message="x",
    )

    # 400k, 800k, then 1.2M: the per-run cap (1M) fires before the soft backstop (2M) would.
    assert sink.events[-1]["code"] == "agent_budget_exceeded"
    assert len(llm.calls) == 3  # the step after the one that crossed the cap never ran


async def test_default_per_run_cost_cap_stops_the_turn(
    seed: SimpleNamespace, db_session: AsyncSession, redis: object
) -> None:
    settings = AgentSettings()  # defaults, no test overrides
    sink = InMemoryEventSink(str(seed.run_id))
    # Output-heavy steps: 600k then 200k tokens. After the first, about 0.26 USD; after the second, 0.32,
    # over the 0.30 default, while the total (800k) is still under the 1M token cap.
    first = _read_step(seed, LLMUsage(prompt=100_000, completion=500_000, total=600_000))
    second = _read_step(seed, LLMUsage(prompt=100_000, completion=100_000, total=200_000))
    llm = FakeLLM(script=[first, second, FakeLLM.respond_text("done")])

    await run_agent_turn(
        _ctx(db_session, redis, llm, sink, settings),
        session_id=str(seed.session.id),
        run_id=str(seed.run_id),
        user_message="x",
    )

    assert sink.events[-1]["code"] == "agent_budget_exceeded"
    assert len(llm.calls) == 2
