"""Unit tests for the agent LLM layer + settings (spec 41)."""

from __future__ import annotations

import pytest

from inkstave.agent.llm.base import LLMError, LLMMessage, LLMResponse, LLMUsage
from inkstave.agent.llm.fake import FakeLLM
from inkstave.agent.llm.openrouter import OpenRouterLLMClient
from inkstave.agent.settings import AgentSettings


async def test_fake_complete_is_scripted_and_records_calls() -> None:
    fake = FakeLLM.scripted([FakeLLM.respond_text("Hello", prompt=3, completion=2)])
    resp = await fake.complete([LLMMessage(role="user", content="hi")], tools=None)
    assert resp.content == "Hello" and resp.finish_reason == "stop"
    assert resp.usage.total == 5
    assert len(fake.calls) == 1 and fake.calls[0]["tools"] is None


async def test_fake_returns_default_when_script_exhausted() -> None:
    fake = FakeLLM()
    resp = await fake.complete([], tools=None)
    assert resp.content == "(fake done)" and resp.finish_reason == "stop"


async def test_fake_stream_is_deterministic() -> None:
    # AC7: >= 2 delta chunks then a terminal chunk with usage + finish_reason.
    fake = FakeLLM.scripted(
        [LLMResponse(content="Hello world", usage=LLMUsage(total=7), finish_reason="stop")],
        stream_chunks=3,
    )
    chunks = [c async for c in fake.stream([LLMMessage(role="user", content="hi")])]
    deltas = [c for c in chunks if c.delta is not None]
    terminal = chunks[-1]
    assert len(deltas) >= 2
    assert "".join(c.delta or "" for c in deltas) == "Hello world"
    assert terminal.finish_reason == "stop" and terminal.usage is not None
    assert terminal.usage.total == 7


def test_agent_settings_load_without_api_key() -> None:
    # AC2: construction must not require the key.
    settings = AgentSettings(openrouter_api_key="")
    assert settings.agent_model
    assert settings.openrouter_api_key == ""


def test_openrouter_client_requires_api_key() -> None:
    # AC2: the real client raises a clear config error when the key is missing.
    with pytest.raises(LLMError):
        OpenRouterLLMClient(AgentSettings(openrouter_api_key=""))


def test_openrouter_client_constructs_with_dummy_key_no_network() -> None:
    # Constructed but never called over the network.
    client = OpenRouterLLMClient(AgentSettings(openrouter_api_key="dummy", agent_model="x/y"))
    assert client.model == "x/y"
