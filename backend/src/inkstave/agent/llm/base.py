"""Provider-agnostic LLM client contract (spec 41).

The graph and nodes depend only on these types — never on the OpenAI SDK. Real
calls go through ``OpenRouterLLMClient``; tests inject ``FakeLLM``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from inkstave.errors import AppError

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)  # already JSON-parsed


class ToolSpec(BaseModel):
    """Lightweight forward declaration; spec 42 fills tool registration."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)  # JSON schema


class LLMMessage(BaseModel):
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None  # populated only from spec 42 onward
    tool_call_id: str | None = None
    name: str | None = None  # tool name for role="tool"


class LLMUsage(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: LLMUsage = Field(default_factory=LLMUsage)
    finish_reason: str | None = None  # "stop" | "tool_calls" | "error" | ...


class LLMStreamChunk(BaseModel):
    delta: str | None = None
    tool_call_delta: dict[str, Any] | None = None
    usage: LLMUsage | None = None
    finish_reason: str | None = None


class LLMError(AppError):
    """A failure reaching/parsing the LLM provider. Callers (spec 44) map it to an event."""

    status_code = 502
    error_type = "llm_error"


@runtime_checkable
class LLMClient(Protocol):
    @property
    def model(self) -> str: ...

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamChunk]: ...
