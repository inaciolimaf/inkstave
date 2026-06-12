"""Deterministic in-memory LLM for tests (spec 41) — no network, ever."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from inkstave.agent.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ToolSpec,
)

ScriptItem = LLMResponse | Callable[[list[LLMMessage]], LLMResponse]

_DEFAULT = LLMResponse(content="(fake done)", finish_reason="stop")


def _split(text: str, parts: int) -> list[str]:
    """Split ``text`` into exactly ``parts`` contiguous slices (some may be empty)."""
    parts = max(parts, 2)
    if not text:
        return [""] * parts
    size = max(1, -(-len(text) // parts))  # ceil
    chunks = [text[i : i + size] for i in range(0, len(text), size)]
    while len(chunks) < parts:
        chunks.append("")
    return chunks


class FakeLLM:
    def __init__(
        self,
        *,
        model: str = "fake/model",
        script: list[ScriptItem] | None = None,
        stream_chunks: int = 3,
    ) -> None:
        self._model = model
        self._script: list[ScriptItem] = list(script or [])
        self._cursor = 0
        self._stream_chunks = stream_chunks
        # Every (messages, tools) the client was called with, for assertions.
        self.calls: list[dict[str, object]] = []

    @property
    def model(self) -> str:
        return self._model

    def _next(self, messages: list[LLMMessage]) -> LLMResponse:
        if self._cursor < len(self._script):
            item = self._script[self._cursor]
            self._cursor += 1
            return item(messages) if callable(item) else item
        return _DEFAULT

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": tools,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self._next(messages)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        self.calls.append({"messages": list(messages), "tools": tools})
        response = self._next(messages)
        for piece in _split(response.content or "", self._stream_chunks):
            yield LLMStreamChunk(delta=piece)
        yield LLMStreamChunk(
            usage=response.usage, finish_reason=response.finish_reason or "stop"
        )

    # --- ergonomics --------------------------------------------------------- #

    @classmethod
    def scripted(cls, responses: list[ScriptItem], **kwargs: object) -> FakeLLM:
        return cls(script=responses, **kwargs)  # type: ignore[arg-type]

    @staticmethod
    def respond_text(text: str, *, prompt: int = 0, completion: int = 0) -> LLMResponse:
        total = prompt + completion
        return LLMResponse(
            content=text,
            finish_reason="stop",
            usage=LLMUsage(prompt=prompt, completion=completion, total=total),
        )
