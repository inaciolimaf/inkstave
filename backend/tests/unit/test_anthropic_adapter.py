"""The real AnthropicLLMClient over a mocked HTTP transport; no network, no real key."""

from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.llm.anthropic_client import AnthropicLLMClient
from inkstave.modules.agent.llm.base import LLMClient, LLMDelta, LLMError, LLMMessage, ToolCall, ToolSpec
from inkstave.modules.agent.llm.factory import build_llm_client
from inkstave.modules.agent.llm.openrouter import OpenRouterLLMClient

DUMMY_KEY = "test-key"
HI = [LLMMessage(role="user", content="hi")]


def _sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _message_events(blocks: list[dict[str, Any]], stop_reason: str) -> list[dict[str, Any]]:
    """The stream of one message: thinking, text and tool_use blocks, then its stop."""
    start = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 3, "output_tokens": 0},
    }
    events: list[dict[str, Any]] = [{"type": "message_start", "message": start}]
    for index, block in enumerate(blocks):
        events += _block_events(index, block)
    events.append(
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 2},
        }
    )
    events.append({"type": "message_stop"})
    return events


def _block_events(index: int, block: dict[str, Any]) -> list[dict[str, Any]]:
    if block["type"] == "text":
        first, delta = {"type": "text", "text": ""}, {"type": "text_delta", "text": block["text"]}
    elif block["type"] == "thinking":
        first = {"type": "thinking", "thinking": "", "signature": ""}
        delta = {"type": "signature_delta", "signature": block["signature"]}
    else:
        first = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
    return [
        {"type": "content_block_start", "index": index, "content_block": first},
        {"type": "content_block_delta", "index": index, "delta": delta},
        {"type": "content_block_stop", "index": index},
    ]


def _client(
    blocks: list[dict[str, Any]], stop_reason: str = "end_turn", status: int = 200
) -> tuple[AnthropicLLMClient, dict[str, Any]]:
    from anthropic import AsyncAnthropic

    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.update(url=request.url, headers=request.headers, json=json.loads(request.content))
        if status != 200:
            return httpx2.Response(status, json={"type": "error", "error": {"type": "x", "message": "boom"}})
        body = _sse(*_message_events(blocks, stop_reason))
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = AnthropicLLMClient(AgentSettings(anthropic_api_key=DUMMY_KEY))
    client._client = AsyncAnthropic(  # type: ignore[attr-defined]
        api_key=DUMMY_KEY,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return client, captured


async def test_defaults_target_haiku_with_the_key_and_no_sampling_parameter() -> None:
    client, captured = _client([{"type": "text", "text": "ok"}])
    resp = await client.complete(HI, temperature=0.2)

    assert client.model == "claude-haiku-5-5"
    assert captured["url"].host == "api.anthropic.com"
    assert captured["url"].path == "/v1/messages"
    assert captured["headers"]["authorization"] == f"Bearer {DUMMY_KEY}"
    body = captured["json"]
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == AgentSettings().agent_max_tokens_per_call
    assert "temperature" not in body
    assert (resp.content, resp.finish_reason) == ("ok", "stop")
    assert (resp.usage.prompt, resp.usage.completion, resp.usage.total) == (3, 2, 5)


async def test_system_goes_top_level_and_tool_results_share_a_user_turn() -> None:
    client, captured = _client([{"type": "text", "text": "ok"}])
    calls = [ToolCall(id="a", name="read", arguments={"p": 1}), ToolCall(id="b", name="read")]
    await client.complete(
        [
            LLMMessage(role="system", content="rules"),
            LLMMessage(role="user", content="go"),
            LLMMessage(role="assistant", tool_calls=calls),
            LLMMessage(role="tool", tool_call_id="a", name="read", content="one"),
            LLMMessage(role="tool", tool_call_id="b", name="read", content=None),
        ],
        tools=[ToolSpec(name="read", description="d")],
    )

    body = captured["json"]
    assert body["system"] == "rules"
    assert body["tools"][0]["input_schema"] == {"type": "object", "properties": {}}
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["messages"][1]["content"][0] == {
        "type": "tool_use",
        "id": "a",
        "name": "read",
        "input": {"p": 1},
    }
    assert body["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "a", "content": "one"},
        {"type": "tool_result", "tool_use_id": "b", "content": ""},
    ]


async def test_tool_call_is_parsed_and_its_thinking_is_replayed_unchanged() -> None:
    blocks = [
        {"type": "thinking", "signature": "sig"},
        {"type": "tool_use", "id": "t1", "name": "read", "input": {"p": "a.tex"}},
    ]
    client, _ = _client(blocks, "tool_use")
    resp = await client.complete(HI)

    assert resp.finish_reason == "tool_calls"
    assert resp.tool_calls == [ToolCall(id="t1", name="read", arguments={"p": "a.tex"})]
    assert resp.provider_blocks is not None

    replay, captured = _client([{"type": "text", "text": "done"}])
    await replay.complete(
        [
            *HI,
            LLMMessage(role="assistant", tool_calls=resp.tool_calls, provider_blocks=resp.provider_blocks),
            LLMMessage(role="tool", tool_call_id="t1", content="x"),
        ]
    )
    thinking, tool_use = captured["json"]["messages"][1]["content"]
    assert thinking == {"type": "thinking", "thinking": "", "signature": "sig"}
    assert tool_use["input"] == {"p": "a.tex"}


async def test_tool_call_cut_by_the_output_cap_is_reported_as_an_error() -> None:
    blocks = [{"type": "tool_use", "id": "t1", "name": "propose_edit", "input": {"new_text": "x"}}]
    client, _ = _client(blocks, "max_tokens")
    resp = await client.complete(HI)

    assert (resp.tool_calls, resp.finish_reason) == ([], "error")


async def test_refusal_fails_loudly() -> None:
    client, _ = _client([], "refusal")
    with pytest.raises(LLMError, match="declined"):
        await client.complete(HI)


async def test_http_failure_becomes_llm_error() -> None:
    client, _ = _client([], status=401)
    with pytest.raises(LLMError):
        await client.complete(HI)


async def test_stream_yields_text_then_usage() -> None:
    client, _ = _client([{"type": "text", "text": "hello"}])
    chunks = [chunk async for chunk in client.stream(HI)]

    assert [c.delta for c in chunks if c.delta] == ["hello"]
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.total == 5


def test_missing_key_names_the_variable() -> None:
    with pytest.raises(LLMError) as excinfo:
        AnthropicLLMClient(AgentSettings(anthropic_api_key=""))
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)


def test_factory_defaults_to_anthropic_and_can_pick_openrouter() -> None:
    default = build_llm_client(AgentSettings(anthropic_api_key=DUMMY_KEY))
    other = build_llm_client(AgentSettings(agent_llm_provider="openrouter", openrouter_api_key=DUMMY_KEY))

    assert isinstance(default, AnthropicLLMClient)
    assert isinstance(default, LLMClient)
    assert isinstance(other, OpenRouterLLMClient)


async def test_complete_reports_text_and_tool_calls_as_they_arrive() -> None:
    blocks = [
        {"type": "text", "text": "Reading."},
        {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "a.tex"}},
    ]
    client, _ = _client(blocks, stop_reason="tool_use")
    seen: list[LLMDelta] = []

    async def collect(delta: LLMDelta) -> None:
        seen.append(delta)

    response = await client.complete(HI, on_delta=collect)

    assert "".join(d.text or "" for d in seen) == "Reading."
    assert [d.tool_name for d in seen if d.tool_name] == ["read_file"]
    assert response.tool_calls[0].arguments == {"path": "a.tex"}  # the whole response still comes back
