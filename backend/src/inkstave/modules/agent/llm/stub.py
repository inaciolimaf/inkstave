"""A deterministic, network-free agent LLM for the e2e smoke tier (spec 54).

``StubAgentLLM`` implements the :class:`~inkstave.modules.agent.llm.base.LLMClient`
protocol but reaches no provider. It drives the agent graph through a fixed
tool-call sequence — **search_project → read_file → propose_edit** — and then a
fixed assistant reply, exactly the shape spec 54 §5.4 requires. The proposed edit
replaces the whole text it read (its `old_text` is that text), so the diff-review UI
always has at least one hunk to apply against the seeded file.

State is derived purely from the conversation passed to ``complete`` (the number
of ``role="tool"`` results so far), so it is robust to retries and needs no
mutable cursor. The document id is read back out of the prior ``search_project``
result, so the stub works against whatever project the e2e seeds.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from uuid import uuid4

from inkstave.modules.agent.llm.base import (
    DeltaHandler,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ToolCall,
    ToolSpec,
)

#: The keyword the stub searches for; the e2e seeds a doc containing it.
SEARCH_QUERY = "Introduction"

#: The replacement body the stub proposes for the text it read — differs from the seeded
#: file so there is always a reviewable hunk.
PROPOSED_TEXT = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\section{Introduction}\n"
    "This paragraph was rewritten by the Inkstave AI agent.\n"
    "\\end{document}\n"
)

#: The fixed assistant reply once the edit is staged.
FINAL_REPLY = (
    "I searched the project, read the document, and prepared a rewrite of the "
    "introduction. Review the proposed diff and apply it when you're ready."
)

_DOC_ID_RE = re.compile(r'"doc_id"\s*:\s*"([0-9a-fA-F-]{36})"')


class StubAgentLLM:
    """Scripted agent LLM: search → read → propose_edit → final reply."""

    def __init__(self, *, model: str = "stub/agent", stream_chunks: int = 3, delay_s: float = 0) -> None:
        self._model = model
        self._stream_chunks = stream_chunks
        self._delay_s = delay_s

    @property
    def model(self) -> str:
        return self._model

    def _plan(self, messages: list[LLMMessage]) -> LLMResponse:
        tool_results = [m for m in messages if m.role == "tool"]
        step = len(tool_results)
        usage = LLMUsage(prompt=1, completion=1, total=2)

        if step == 0:
            return _tool_call("search_project", {"query": SEARCH_QUERY}, usage)

        doc_id = _first_doc_id(tool_results)
        if doc_id is None:
            # Search found nothing to edit — answer in prose rather than loop.
            return LLMResponse(
                content="I couldn't find a document to edit in this project.",
                finish_reason="stop",
                usage=usage,
            )

        if step == 1:
            return _tool_call("read_file", {"doc_id": doc_id}, usage)
        if step == 2:
            # The whole read text is replaced, so old_text is the document as read (it is unique).
            old_text = _read_content(tool_results[-1])
            return _tool_call(
                "propose_edit",
                {"doc_id": doc_id, "old_text": old_text, "new_text": PROPOSED_TEXT},
                usage,
            )
        return LLMResponse(content=FINAL_REPLY, finish_reason="stop", usage=usage)

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        on_delta: DeltaHandler | None = None,
    ) -> LLMResponse:
        await asyncio.sleep(self._delay_s)
        return self._plan(messages)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        await asyncio.sleep(self._delay_s)
        response = self._plan(messages)
        text = response.content or ""
        size = max(1, -(-len(text) // max(self._stream_chunks, 1)))
        for i in range(0, len(text), size):
            yield LLMStreamChunk(delta=text[i : i + size])
        yield LLMStreamChunk(usage=response.usage, finish_reason=response.finish_reason or "stop")


def _tool_call(name: str, args: dict[str, object], usage: LLMUsage) -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall(id=uuid4().hex, name=name, arguments=args)],
        finish_reason="tool_calls",
        usage=usage,
    )


_FRAME = re.compile(r"^<untrusted_tool_result>\n(.*)\n</untrusted_tool_result>$", re.DOTALL)


def _read_content(read_result: LLMMessage) -> str:
    """The `content` of a `read_file` result (the text as it was read), or "" when unreadable.

    The graph frames tool results as untrusted text before the provider sees them (spec 49), so the
    JSON comes wrapped in that frame; unwrap it the way the provider would read it.
    """
    raw = read_result.content or "{}"
    framed = _FRAME.match(raw)
    try:
        data = json.loads(framed.group(1) if framed else raw).get("data") or {}
    except (json.JSONDecodeError, AttributeError):
        return ""
    content = data.get("content")
    return content if isinstance(content, str) else ""


def _first_doc_id(tool_results: list[LLMMessage]) -> str | None:
    for message in tool_results:
        match = _DOC_ID_RE.search(message.content or "")
        if match:
            return match.group(1)
    return None
