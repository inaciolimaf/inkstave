"""Spec 67: exercise the real OpenRouterLLMClient over a mocked HTTP transport.

No network and no API key required — the OpenAI SDK is pointed at an
``httpx.MockTransport`` so every mapping/parsing path on the real class runs, but
the socket is faked. The live smoke (``just agent-live``) is a separate manual
check, deselected by default via the ``live`` marker.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from inkstave.agent.llm.base import LLMClient, LLMError, LLMMessage, ToolSpec
from inkstave.agent.llm.fake import FakeLLM
from inkstave.agent.llm.openrouter import OpenRouterLLMClient
from inkstave.agent.settings import AgentSettings

DUMMY_KEY = "dummy-key-not-real"


def _completion_json(
    *,
    content: str | None = "Hi there",
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
        message["content"] = None
    return {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "x/y",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


def _sse(*events: dict[str, Any]) -> bytes:
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    body += "data: [DONE]\n\n"
    return body.encode()


def _chunk(content: str | None = None, finish_reason: str | None = None) -> dict[str, Any]:
    delta = {"content": content} if content is not None else {}
    return {
        "id": "c",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "x/y",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _usage_event() -> dict[str, Any]:
    return {
        "id": "c",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "x/y",
        "choices": [],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


def _client_with_transport(
    handler: Any, **settings_over: Any
) -> tuple[OpenRouterLLMClient, dict[str, Any]]:
    """Build the real client, then swap its OpenAI SDK for one over a mock socket."""
    from openai import AsyncOpenAI

    settings = AgentSettings(openrouter_api_key=DUMMY_KEY, **settings_over)
    client = OpenRouterLLMClient(settings)
    captured: dict[str, Any] = {}

    def capturing(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        captured["headers"] = request.headers
        captured["json"] = json.loads(request.content)
        return handler(request)

    # Swap the SDK for one over a mock socket so the real mapping/parsing runs but
    # no network is touched; `capturing` records each request for assertions.
    client._client = AsyncOpenAI(  # type: ignore[attr-defined]
        api_key=DUMMY_KEY,
        base_url=settings.openrouter_base_url,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(capturing)),
    )
    return client, captured


async def test_complete_targets_openrouter_url_model_params() -> None:  # AC1
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_json())

    client, captured = _client_with_transport(handler, agent_model="x/y")
    await client.complete([LLMMessage(role="user", content="hi")])

    assert str(captured["url"]).endswith("/chat/completions")
    assert captured["url"].host == "openrouter.ai"
    body = captured["json"]
    assert body["model"] == "x/y"
    assert body["temperature"] == AgentSettings().agent_temperature
    assert body["max_tokens"] == AgentSettings().agent_max_tokens_per_call


async def test_complete_sends_auth_and_identification_headers() -> None:  # AC2
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_json())

    client, captured = _client_with_transport(handler)
    await client.complete([LLMMessage(role="user", content="hi")])

    headers = captured["headers"]
    assert headers["authorization"] == f"Bearer {DUMMY_KEY}"
    assert headers["http-referer"] == AgentSettings().agent_http_referer
    assert headers["x-title"] == AgentSettings().agent_app_title


async def test_complete_maps_response_content_usage_finish() -> None:  # AC3
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_json(content="Mapped", finish_reason="stop"))

    client, _ = _client_with_transport(handler)
    resp = await client.complete([LLMMessage(role="user", content="hi")])

    assert resp.content == "Mapped"
    assert resp.finish_reason == "stop"
    assert resp.usage.prompt == 3
    assert resp.usage.completion == 2
    assert resp.usage.total == 5


async def test_complete_malformed_tool_args_do_not_raise() -> None:  # AC4
    bad_tool = {
        "id": "t1",
        "type": "function",
        "function": {"name": "search", "arguments": "{not valid json"},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_completion_json(tool_calls=[bad_tool], finish_reason="tool_calls")
        )

    client, _ = _client_with_transport(handler)
    resp = await client.complete(
        [LLMMessage(role="user", content="hi")],
        tools=[ToolSpec(name="search", description="d")],
    )

    assert resp.finish_reason == "error"  # recorded, not raised
    assert resp.tool_calls[0].arguments == {"_raw": "{not valid json"}


async def test_stream_sets_stream_flags_and_parses_sse() -> None:  # AC5
    def handler(_request: httpx.Request) -> httpx.Response:
        body = _sse(
            _chunk("Hello "),
            _chunk("World"),
            _chunk(finish_reason="stop"),
            _usage_event(),
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    client, captured = _client_with_transport(handler)
    chunks = [c async for c in client.stream([LLMMessage(role="user", content="hi")])]

    body = captured["json"]
    assert body["stream"] is True
    assert body["stream_options"]["include_usage"] is True

    deltas = [c.delta for c in chunks if c.delta]
    assert "".join(deltas) == "Hello World"  # order preserved, full text
    assert any(c.finish_reason == "stop" for c in chunks)
    assert chunks[-1].usage is not None and chunks[-1].usage.total == 5  # terminal usage


async def test_stream_chunks_become_agent_tokens() -> None:  # AC6
    def handler(_request: httpx.Request) -> httpx.Response:
        body = _sse(
            _chunk("The "),
            _chunk("quick "),
            _chunk("fox"),
            _chunk(finish_reason="stop"),
            _usage_event(),
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    client, _ = _client_with_transport(handler)
    # The stream-chunk → token wiring: each non-empty delta is an ordered token.
    tokens = [
        c.delta async for c in client.stream([LLMMessage(role="user", content="hi")]) if c.delta
    ]
    assert tokens == ["The ", "quick ", "fox"]


def test_missing_key_raises_friendly_llm_error() -> None:  # AC7
    with pytest.raises(LLMError) as excinfo:
        OpenRouterLLMClient(AgentSettings(openrouter_api_key=""))
    assert "OPENROUTER_API_KEY" in str(excinfo.value)


def test_fake_llm_satisfies_protocol_and_is_di_default() -> None:  # AC8
    # FakeLLM is a structural LLMClient — the DI default for every fast-suite test.
    assert isinstance(FakeLLM(), LLMClient)
    # The real client is also an LLMClient, but constructing it needs a key, so the
    # fast suite must never reach it (it is overridden to FakeLLM in the app/agent
    # fixtures — see conftest / agent test wiring).
    assert isinstance(OpenRouterLLMClient(AgentSettings(openrouter_api_key=DUMMY_KEY)), LLMClient)
