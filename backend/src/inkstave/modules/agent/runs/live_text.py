"""Forwards a model call to the event stream while it runs, in batches a browser can draw."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inkstave.modules.agent.llm.base import LLMDelta
    from inkstave.modules.agent.runs.events import EventSink

# Providers send a few words at a time; each `token` redraws the transcript's Markdown.
_TOKEN_INTERVAL_S = 0.08
# A long tool call or a long think sends no text, and the user must still see it is alive.
_STATUS_INTERVAL_S = 2.0


class LiveText:
    """The `on_delta` of one model call: ``streamed`` says whether any text went out."""

    def __init__(self, events: EventSink) -> None:
        self._events = events
        self._buffer: list[str] = []
        self._stage = "thinking"
        self._tool: str | None = None
        self._last_token = 0.0
        self._last_status = time.monotonic()
        self.streamed = False

    async def __call__(self, delta: LLMDelta) -> None:
        if delta.text:
            await self._add_text(delta.text)
        elif delta.tool_name:
            await self.flush()
            self._stage, self._tool = "tool_input", delta.tool_name
            await self._status()
        elif time.monotonic() - self._last_status >= _STATUS_INTERVAL_S:
            await self._status()

    async def _add_text(self, text: str) -> None:
        self._buffer.append(text)
        self.streamed = True
        if time.monotonic() - self._last_token >= _TOKEN_INTERVAL_S:
            await self.flush()

    async def _status(self) -> None:
        self._last_status = time.monotonic()
        await self._events.emit("status", stage=self._stage, tool=self._tool)

    async def flush(self) -> None:
        """Send what is waiting; the caller does this last, so no text stays behind."""
        if not self._buffer:
            return
        text = "".join(self._buffer)
        self._buffer.clear()
        self._last_token = time.monotonic()
        await self._events.emit("token", text=text)
