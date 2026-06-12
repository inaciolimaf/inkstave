"""SSE forwarding of agent run events (spec 44)."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.agent.api.events import TERMINAL_TYPES, last_event_key, run_channel

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _sse(data: dict[str, Any]) -> bytes:
    return f"event: {data['type']}\ndata: {json.dumps(data, default=str)}\n\n".encode()


async def sse_stream(
    redis: Redis, run_id: UUID | str, heartbeat_seconds: int
) -> AsyncIterator[bytes]:
    """Forward a run's events as SSE frames, replaying the terminal for late subscribers."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(run_channel(run_id))
    poll = min(0.1, float(heartbeat_seconds))
    last_ping = time.monotonic()

    async def _replay_terminal() -> dict[str, Any] | None:
        raw = await redis.get(last_event_key(run_id))
        return json.loads(raw) if raw is not None else None

    try:
        # If the run already finished, replay the stored terminal event and close.
        terminal = await _replay_terminal()
        if terminal is not None:
            yield _sse(terminal)
            return

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll)
            if message is None:
                # No live event — close the race by re-checking the terminal key.
                terminal = await _replay_terminal()
                if terminal is not None:
                    yield _sse(terminal)
                    return
                if time.monotonic() - last_ping >= heartbeat_seconds:
                    yield b": ping\n\n"
                    last_ping = time.monotonic()
                continue
            event = json.loads(message["data"])
            yield _sse(event)
            last_ping = time.monotonic()
            if event.get("type") in TERMINAL_TYPES:
                return
    finally:
        await pubsub.unsubscribe(run_channel(run_id))
        await pubsub.aclose()
