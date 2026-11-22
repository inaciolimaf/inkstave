"""A deterministic, network-free agent LLM for the e2e smoke tier (spec 54).

``StubAgentLLM`` implements the :class:`~inkstave.modules.agent.llm.base.LLMClient` protocol but
reaches no provider. It plays one named script from :mod:`inkstave.modules.agent.scripted.scenarios`,
chosen by ``LLM_STUB_SCENARIO`` (test only). The default, ``happy``, is the fixed
**search_project → read_file → propose_edit → reply** sequence of spec 54. The other scenarios
make one mistake a real model makes, so an e2e flow can see how the panel and the review react.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from inkstave.modules.agent.llm.base import (
    DeltaHandler,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    ToolSpec,
)
from inkstave.modules.agent.scripted.scenarios import FINAL_REPLY, PROPOSED_TEXT, SEARCH_QUERY, scenario_steps
from inkstave.modules.agent.scripted.steps import ScriptedLLM

__all__ = ["FINAL_REPLY", "PROPOSED_TEXT", "SEARCH_QUERY", "StubAgentLLM"]


class StubAgentLLM:
    """Scripted agent LLM for the e2e tier: one named scenario, no network."""

    def __init__(self, *, model: str = "stub/agent", delay_s: float = 0, scenario: str = "happy") -> None:
        self._model = model
        self._delay_s = delay_s
        # Built here so an unknown scenario name fails at worker start, not at the first run.
        self._script = ScriptedLLM(scenario_steps(scenario), model=model, keep_calls=False)

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        on_delta: DeltaHandler | None = None,
    ) -> LLMResponse:
        await asyncio.sleep(self._delay_s)
        return await self._script.complete(messages, on_delta=on_delta)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        await asyncio.sleep(self._delay_s)
        async for chunk in self._script.stream(messages):
            yield chunk
