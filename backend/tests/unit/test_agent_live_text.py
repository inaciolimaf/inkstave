"""LiveText batches a model call for the browser and never loses text."""

from __future__ import annotations

import pytest

from inkstave.modules.agent.llm.base import LLMDelta
from inkstave.modules.agent.runs import live_text
from inkstave.modules.agent.runs.events import InMemoryEventSink
from inkstave.modules.agent.runs.live_text import LiveText


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(live_text, "time", fake)
    return fake


def _sent(sink: InMemoryEventSink, kind: str) -> list[dict[str, object]]:
    return [e for e in sink.events if e["type"] == kind]


async def test_text_is_batched_and_nothing_stays_behind(clock: _Clock) -> None:
    sink = InMemoryEventSink("r")
    live = LiveText(sink)
    for word in ("a", "b", "c"):
        await live(LLMDelta(text=word))
    assert [e["text"] for e in _sent(sink, "token")] == ["a"]

    clock.now += 0.1
    await live(LLMDelta(text="d"))
    await live(LLMDelta(text="e"))
    await live.flush()
    assert [e["text"] for e in _sent(sink, "token")] == ["a", "bcd", "e"]
    assert live.streamed


async def test_a_tool_call_sends_the_text_before_it_and_names_itself(clock: _Clock) -> None:
    sink = InMemoryEventSink("r")
    live = LiveText(sink)
    clock.now += 1
    await live(LLMDelta(text="x"))
    await live(LLMDelta(text="y"))
    await live(LLMDelta(tool_name="propose_edit"))
    kinds = [e["type"] for e in sink.events]
    assert kinds == ["token", "token", "status"]
    assert _sent(sink, "status")[0]["stage"] == "tool_input"


async def test_a_silent_stretch_still_shows_signs_of_life_at_a_bounded_rate(clock: _Clock) -> None:
    sink = InMemoryEventSink("r")
    live = LiveText(sink)
    await live(LLMDelta())
    assert _sent(sink, "status") == []
    clock.now += 2.5
    await live(LLMDelta())
    await live(LLMDelta())
    assert len(_sent(sink, "status")) == 1
    assert not live.streamed
