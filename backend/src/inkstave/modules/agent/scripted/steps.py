"""Scripted models: one turn's model behaviour written by hand, mistakes included.

Used by the scenario tests (``backend/tests/agent_scenarios``) and by the e2e stub
(``LLM_STUB_SCENARIO``). No network and no provider. A script is a sequence of steps, one per
model call of a turn. The step is read from the conversation itself (the assistant messages
written since the last user message), so one script serves any number of runs and keeps no
state between them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from inkstave.modules.agent.llm.base import (
    DeltaHandler,
    LLMDelta,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ToolCall,
    ToolSpec,
)

_USAGE = LLMUsage(prompt=1, completion=1, total=2)


class Step(Protocol):
    """One model call. ``play`` may stream through ``on_delta`` and then return or raise."""

    async def play(self, messages: list[LLMMessage], on_delta: DeltaHandler | None) -> LLMResponse: ...


async def _send(on_delta: DeltaHandler | None, pieces: Sequence[str]) -> None:
    """Stream text pieces the way a provider does, one delta each."""
    if on_delta is None:
        return
    for piece in pieces:
        await on_delta(LLMDelta(text=piece))


@dataclass(frozen=True)
class Reply:
    """A final answer. ``deltas`` are sent as they arrive; without them the graph chunks ``text``."""

    text: str | None
    deltas: tuple[str, ...] = ()

    async def play(self, messages: list[LLMMessage], on_delta: DeltaHandler | None) -> LLMResponse:
        await _send(on_delta, self.deltas)
        return LLMResponse(content=self.text, finish_reason="stop", usage=_USAGE)


@dataclass(frozen=True)
class Call:
    """One tool call. ``raw`` replaces the arguments with text that is not JSON, as a provider returns it."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw: str | None = None

    def to_tool_call(self) -> ToolCall:
        if self.raw is None:
            return ToolCall(id=uuid4().hex, name=self.name, arguments=self.arguments)
        # OpenRouter keeps unparseable arguments as `_raw` and marks the response as an error.
        return ToolCall(id=uuid4().hex, name=self.name, arguments={"_raw": self.raw})


@dataclass(frozen=True)
class Calls:
    """One model response with one or more tool calls, optionally preceded by narration."""

    calls: tuple[Call, ...]
    text: str | None = None

    async def play(self, messages: list[LLMMessage], on_delta: DeltaHandler | None) -> LLMResponse:
        await _send(on_delta, [self.text] if self.text else [])
        malformed = any(c.raw is not None for c in self.calls)
        return LLMResponse(
            content=self.text,
            tool_calls=[c.to_tool_call() for c in self.calls],
            finish_reason="error" if malformed else "tool_calls",
            usage=_USAGE,
        )


@dataclass(frozen=True)
class Stream:
    """Text starts to arrive and then the call fails: a dropped connection, a timeout, a crash."""

    deltas: tuple[str, ...]
    error: BaseException

    async def play(self, messages: list[LLMMessage], on_delta: DeltaHandler | None) -> LLMResponse:
        await _send(on_delta, self.deltas)
        raise self.error


@dataclass(frozen=True)
class Do:
    """Something happens in the world first (a collaborator edits, a user cancels), then the model answers."""

    action: Callable[[], Awaitable[None]]
    then: Step

    async def play(self, messages: list[LLMMessage], on_delta: DeltaHandler | None) -> LLMResponse:
        await self.action()
        return await self.then.play(messages, on_delta)


@dataclass(frozen=True)
class Compute:
    """A step worked out from the conversation so far: a doc id from the search, the text just read."""

    make: Callable[[list[LLMMessage]], Step]

    async def play(self, messages: list[LLMMessage], on_delta: DeltaHandler | None) -> LLMResponse:
        return await self.make(messages).play(messages, on_delta)


def turn_step_index(messages: list[LLMMessage]) -> int:
    """How many model calls this turn has made: the assistant messages since the last user message."""
    last_user = max((i for i, m in enumerate(messages) if m.role == "user"), default=-1)
    return sum(1 for m in messages[last_user + 1 :] if m.role == "assistant")


class ScriptedLLM:
    """An LLM client that plays ``steps`` in order, then ``tail`` for every call after them."""

    def __init__(
        self,
        steps: Sequence[Step],
        *,
        tail: Step | None = None,
        model: str = "scripted/model",
        keep_calls: bool = True,
    ) -> None:
        self._steps = tuple(steps)
        self._tail: Step = tail or Reply("(scripted done)")
        self._model = model
        self._keep_calls = keep_calls
        # Every transcript the model was shown, in call order, for assertions (off for the long-lived stub).
        self.calls: list[list[LLMMessage]] = []

    @property
    def model(self) -> str:
        return self._model

    def _step_for(self, messages: list[LLMMessage]) -> Step:
        index = turn_step_index(messages)
        return self._steps[index] if index < len(self._steps) else self._tail

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        on_delta: DeltaHandler | None = None,
    ) -> LLMResponse:
        if self._keep_calls:
            self.calls.append(list(messages))
        return await self._step_for(messages).play(messages, on_delta)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        response = await self.complete(messages)
        text = response.content or ""
        for start in range(0, len(text), 16):
            yield LLMStreamChunk(delta=text[start : start + 16])
        yield LLMStreamChunk(usage=response.usage, finish_reason=response.finish_reason or "stop")
