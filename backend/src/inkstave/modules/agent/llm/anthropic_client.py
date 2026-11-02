"""Anthropic-backed LLM client: the official SDK against the Claude API.

Maps the provider-agnostic types to and from the Messages API. ``complete`` streams
under the hood, because one call can write a whole document and the output cap is high.
Sampling parameters are never sent: current Claude models reject them.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from inkstave.modules.agent.llm.base import (
    DeltaHandler,
    LLMDelta,
    LLMError,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ToolCall,
    ToolSpec,
)

if TYPE_CHECKING:
    from inkstave.core.config.agent import AgentSettings

logger = logging.getLogger("inkstave.agent.llm")

_FINISH_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
}


def _assistant_content(message: LLMMessage) -> list[dict[str, Any]]:
    """The blocks of an assistant turn, replaying the provider's own when it has them."""
    if message.provider_blocks:
        return message.provider_blocks
    has_text = message.content is not None and message.content.strip()
    blocks: list[dict[str, Any]] = [{"type": "text", "text": message.content}] if has_text else []
    blocks.extend(
        {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
        for call in message.tool_calls or []
    )
    return blocks


def _tool_result_content(message: LLMMessage) -> str | list[dict[str, Any]]:
    """Plain text, or text plus image blocks when the tool returned images."""
    text = message.content or ""
    if not message.images:
        return text
    images = [
        {"type": "image", "source": {"type": "base64", "media_type": i.media_type, "data": i.data}}
        for i in message.images
    ]
    return [{"type": "text", "text": text}, *images]


def _append_tool_result(out: list[dict[str, Any]], message: LLMMessage) -> None:
    """Add a tool result; results of one assistant turn share a single user message."""
    block = {
        "type": "tool_result",
        "tool_use_id": message.tool_call_id,
        "content": _tool_result_content(message),
    }
    if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
        out[-1]["content"].append(block)
    else:
        out.append({"role": "user", "content": [block]})


def _append_message(out: list[dict[str, Any]], message: LLMMessage) -> None:
    if message.role == "tool":
        _append_tool_result(out, message)
    elif message.role == "assistant":
        blocks = _assistant_content(message)
        if blocks:
            out.append({"role": "assistant", "content": blocks})
    elif message.content:
        out.append({"role": "user", "content": message.content})


def _to_anthropic_messages(messages: list[LLMMessage]) -> tuple[str, list[dict[str, Any]]]:
    """The top-level system prompt, and the turns the Messages API takes."""
    system = "\n\n".join(m.content for m in messages if m.role == "system" and m.content)
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.role != "system":
            _append_message(out, message)
    return system, out


def _to_anthropic_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


async def _forward(stream: Any, on_delta: DeltaHandler) -> None:
    async for event in stream:
        delta = _delta_of(event)
        if delta is not None:
            await on_delta(delta)


def _usage_of(usage: Any) -> LLMUsage:
    prompt, completion = usage.input_tokens or 0, usage.output_tokens or 0
    return LLMUsage(prompt=prompt, completion=completion, total=prompt + completion)


def _to_response(message: Any) -> LLMResponse:
    """Our response for a finished message; a refusal or a cut-off tool call fails loudly."""
    if message.stop_reason == "refusal":
        raise LLMError("The model declined this request.")
    text = "".join(b.text for b in message.content if b.type == "text")
    calls = [
        ToolCall(id=b.id, name=b.name, arguments=b.input) for b in message.content if b.type == "tool_use"
    ]
    finish_reason = _FINISH_REASONS.get(message.stop_reason, message.stop_reason)
    if calls and finish_reason == "length":
        # The output cap cut the call short, so its arguments cannot be trusted.
        logger.warning("anthropic: tool call truncated by max_tokens (model=%s)", message.model)
        calls, finish_reason = [], "error"
    return LLMResponse(
        content=text or None,
        tool_calls=calls,
        usage=_usage_of(message.usage),
        finish_reason=finish_reason,
        provider_blocks=[b.model_dump(mode="json", exclude_none=True) for b in message.content],
    )


def _delta_of(event: Any) -> LLMDelta | None:
    """What a stream event tells the user, if anything."""
    if event.type == "text":
        return LLMDelta(text=event.text)
    if event.type == "content_block_start" and event.content_block.type == "tool_use":
        return LLMDelta(tool_name=event.content_block.name)
    return LLMDelta() if event.type in ("thinking", "input_json") else None


class AnthropicLLMClient:
    def __init__(self, settings: AgentSettings) -> None:
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is required to construct the Anthropic LLM client.")
        from anthropic import AsyncAnthropic

        self._model = settings.agent_model
        self._max_tokens = settings.agent_max_tokens_per_call
        self._client: Any = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.agent_request_timeout_s,
        )

    @property
    def model(self) -> str:
        return self._model

    def _params(
        self, messages: list[LLMMessage], tools: list[ToolSpec] | None, max_tokens: int | None
    ) -> dict[str, Any]:
        system, turns = _to_anthropic_messages(messages)
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
            "messages": turns,
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = _to_anthropic_tools(tools)
        return params

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,  # part of the protocol; never sent
        max_tokens: int | None = None,
        on_delta: DeltaHandler | None = None,
    ) -> LLMResponse:
        try:
            async with self._client.messages.stream(**self._params(messages, tools, max_tokens)) as stream:
                if on_delta is not None:
                    await _forward(stream, on_delta)
                message = await stream.get_final_message()
        except Exception as exc:  # any network/SDK error
            logger.exception("anthropic complete failed")
            raise LLMError(f"LLM request failed: {exc}") from exc
        return _to_response(message)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,  # part of the protocol; never sent
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        try:
            async with self._client.messages.stream(**self._params(messages, tools, max_tokens)) as stream:
                async for text in stream.text_stream:
                    yield LLMStreamChunk(delta=text)
                message = await stream.get_final_message()
        except Exception as exc:
            logger.exception("anthropic stream failed")
            raise LLMError(f"LLM stream failed: {exc}") from exc
        yield LLMStreamChunk(
            usage=_usage_of(message.usage),
            finish_reason=_FINISH_REASONS.get(message.stop_reason, message.stop_reason),
        )
