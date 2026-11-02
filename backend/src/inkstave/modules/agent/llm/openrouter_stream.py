"""Rebuilds a whole chat completion from its stream, forwarding it as it arrives."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from inkstave.modules.agent.llm.base import DeltaHandler, LLMDelta

if TYPE_CHECKING:
    from collections.abc import AsyncIterable


@dataclass
class _PartialCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class _Assembly:
    text: list[str] = field(default_factory=list)
    calls: dict[int, _PartialCall] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: Any = None

    def result(self) -> tuple[Any, Any]:
        """A choice shaped like the non-streaming SDK's, and the usage."""
        calls = [
            SimpleNamespace(id=c.id, function=SimpleNamespace(name=c.name, arguments=c.arguments))
            for _, c in sorted(self.calls.items())
        ]
        message = SimpleNamespace(content="".join(self.text) or None, tool_calls=calls or None)
        return SimpleNamespace(message=message, finish_reason=self.finish_reason), self.usage


async def _add_call_part(assembly: _Assembly, part: Any, on_delta: DeltaHandler) -> None:
    call = assembly.calls.setdefault(getattr(part, "index", 0) or 0, _PartialCall())
    function = part.function
    call.id = part.id or call.id
    call.arguments += (function.arguments or "") if function else ""
    if function and function.name and not call.name:
        call.name = function.name
        await on_delta(LLMDelta(tool_name=call.name))
    else:
        await on_delta(LLMDelta())


async def _add_choice(assembly: _Assembly, choice: Any, on_delta: DeltaHandler) -> None:
    assembly.finish_reason = choice.finish_reason or assembly.finish_reason
    text = getattr(choice.delta, "content", None)
    if text:
        assembly.text.append(text)
        await on_delta(LLMDelta(text=text))
    for part in getattr(choice.delta, "tool_calls", None) or []:
        await _add_call_part(assembly, part, on_delta)


async def collect_stream(stream: AsyncIterable[Any], on_delta: DeltaHandler) -> tuple[Any, Any]:
    assembly = _Assembly()
    async for event in stream:
        assembly.usage = getattr(event, "usage", None) or assembly.usage
        if event.choices:
            await _add_choice(assembly, event.choices[0], on_delta)
    return assembly.result()
