"""OpenRouter-backed LLM client (spec 41): OpenAI SDK pointed at OpenRouter.

Never instantiated in tests. Maps the provider-agnostic types to/from the OpenAI
chat API; malformed tool arguments are recorded, never raised.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from inkstave.agent.llm.base import (
    LLMError,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ToolCall,
    ToolSpec,
)

if TYPE_CHECKING:
    from inkstave.agent.settings import AgentSettings

logger = logging.getLogger("inkstave.agent.llm")


def _usage_of(usage: Any) -> LLMUsage | None:
    """Token counts from an SDK usage object, or ``None`` when it carries none."""
    if usage is None:
        return None
    return LLMUsage(
        prompt=getattr(usage, "prompt_tokens", 0) or 0,
        completion=getattr(usage, "completion_tokens", 0) or 0,
        total=getattr(usage, "total_tokens", 0) or 0,
    )


def _overrides(temperature: float | None, max_tokens: int | None) -> dict[str, Any]:
    """Per-call overrides; an unset value keeps the client's configured default."""
    over: dict[str, Any] = {}
    if temperature is not None:
        over["temperature"] = temperature
    if max_tokens is not None:
        over["max_tokens"] = max_tokens
    return over


class OpenRouterLLMClient:
    def __init__(self, settings: AgentSettings) -> None:
        if not settings.openrouter_api_key:
            raise LLMError("OPENROUTER_API_KEY is required to construct the OpenRouter LLM client.")
        from openai import AsyncOpenAI

        self._model = settings.agent_model
        self._temperature = settings.agent_temperature
        self._max_tokens = settings.agent_max_tokens_per_call
        self._client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=settings.agent_request_timeout_s,
        )
        self._headers = {
            "HTTP-Referer": settings.agent_http_referer,
            "X-Title": settings.agent_app_title,
        }

    @property
    def model(self) -> str:
        return self._model

    # --- request mapping ---------------------------------------------------- #

    @staticmethod
    def _to_openai_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            entry: dict[str, Any] = {"role": m.role, "content": m.content or ""}
            if m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id is not None:
                entry["tool_call_id"] = m.tool_call_id
            if m.name is not None:
                entry["name"] = m.name
            out.append(entry)
        return out

    @staticmethod
    def _to_openai_tools(tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    @staticmethod
    def _parse_tool_calls(raw_calls: Any) -> tuple[list[ToolCall], bool]:
        calls: list[ToolCall] = []
        had_error = False
        for tc in raw_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    raise ValueError("tool arguments are not an object")
            except (ValueError, TypeError):
                had_error = True
                args = {"_raw": getattr(tc.function, "arguments", None)}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return calls, had_error

    # --- API ---------------------------------------------------------------- #

    async def _create(self, messages: list[LLMMessage], **overrides: Any) -> Any:
        """One chat-completions call with this client's defaults applied."""
        params: dict[str, Any] = {
            "model": self._model,
            "messages": self._to_openai_messages(messages),
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "extra_headers": self._headers,
        }
        params.update(overrides)
        return await cast("Any", self._client).chat.completions.create(**params)

    def _check_tool_calls(self, choice: Any, tool_calls: list[ToolCall], had_error: bool) -> bool:
        """Whether the response must be reported as an error (spec 41 §4)."""
        if choice.finish_reason == "tool_calls" and not tool_calls:
            # The provider signalled a tool call but none survived parsing — e.g. some
            # providers (seen with DeepSeek via SiliconFlow) return the call in a shape
            # the SDK does not surface as ``message.tool_calls``. Without this the turn
            # would silently end as a plain-text answer with no proposed edit and no
            # error. Mark it as an error and log the raw message so we can diagnose.
            logger.warning(
                "openrouter: finish_reason=tool_calls but no parseable tool_calls "
                "(model=%s); raw message=%r",
                self._model,
                choice.message,
            )
            return True
        if had_error:
            logger.warning("openrouter: malformed tool-call arguments (model=%s)", self._model)
        return had_error

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        try:
            resp = await self._create(
                messages,
                tools=self._to_openai_tools(tools),
                **_overrides(temperature, max_tokens),
            )
        except Exception as exc:  # any network/SDK error
            logger.exception("openrouter complete failed")
            raise LLMError(f"LLM request failed: {exc}") from exc

        choice = resp.choices[0]
        tool_calls, had_error = self._parse_tool_calls(choice.message.tool_calls)
        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            usage=_usage_of(resp.usage) or LLMUsage(),
            finish_reason=(
                "error"
                if self._check_tool_calls(choice, tool_calls, had_error)
                else choice.finish_reason
            ),
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        try:
            stream = await self._create(
                messages,
                tools=self._to_openai_tools(tools),
                stream=True,
                stream_options={"include_usage": True},
                **_overrides(temperature, max_tokens),
            )
        except Exception as exc:
            logger.exception("openrouter stream failed")
            raise LLMError(f"LLM stream failed: {exc}") from exc

        async for event in stream:
            usage = _usage_of(getattr(event, "usage", None))
            if not event.choices:
                if usage is not None:
                    yield LLMStreamChunk(usage=usage)
                continue
            yield LLMStreamChunk(
                delta=getattr(event.choices[0].delta, "content", None),
                tool_call_delta=None,
                usage=usage,
                finish_reason=event.choices[0].finish_reason,
            )
