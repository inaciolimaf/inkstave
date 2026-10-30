"""Shared plumbing for the Redis-pub/sub-backed SSE endpoints.

Three streams (compile, project import, agent run) all forward published JSON
payloads as SSE frames and interleave a periodic keep-alive. The polling loop and
the keep-alive clock live here so each stream module only owns its own framing
and terminal condition.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any


class Keepalive:
    """Rate-limits keep-alive frames to at most one per `seconds`."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._last = time.monotonic()

    def due(self) -> bool:
        """True (and rearms) once the interval has elapsed since the last frame."""
        if time.monotonic() - self._last < self.seconds:
            return False
        self._last = time.monotonic()
        return True

    def reset(self) -> None:
        """Restart the interval — call it whenever a real frame is sent."""
        self._last = time.monotonic()


async def event_pump(pubsub: Any, poll: float) -> AsyncIterator[dict[str, Any] | None]:
    """Yield each published payload, or ``None`` on an idle poll.

    The poll is deliberately short (so a transient empty read never masquerades as
    a keep-alive); the caller decides how often an idle poll becomes a frame.
    """
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll)
        yield json.loads(message["data"]) if message is not None else None
