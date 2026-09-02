"""SSE forwarding of agent run events (spec 44)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.agent.api.events import TERMINAL_TYPES, last_event_key, run_channel
from inkstave.sse import Keepalive, event_pump

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _sse(data: dict[str, Any]) -> bytes:
    return f"event: {data['type']}\ndata: {json.dumps(data, default=str)}\n\n".encode()


async def _replay_terminal(redis: Redis, run_id: UUID | str) -> dict[str, Any] | None:
    """The stored terminal event for a run that already finished, if any."""
    raw = await redis.get(last_event_key(run_id))
    return json.loads(raw) if raw is not None else None


async def _events(
    redis: Redis, run_id: UUID | str, pubsub: Any, heartbeat: Keepalive
) -> AsyncIterator[dict[str, Any] | None]:
    """Published events, ending with the replayed terminal once the channel is idle.

    Yields ``None`` when nothing arrived and only a heartbeat is due.
    """
    async for event in event_pump(pubsub, poll=min(0.1, heartbeat.seconds)):
        if event is not None:
            yield event
            continue
        # No live event — close the race by re-checking the terminal key.
        terminal = await _replay_terminal(redis, run_id)
        if terminal is not None:
            yield terminal
            return
        if heartbeat.due():
            yield None


async def _frames(
    redis: Redis, run_id: UUID | str, pubsub: Any, heartbeat: Keepalive
) -> AsyncIterator[bytes]:
    """SSE frames for one run, from the first event to the terminal one."""
    # If the run already finished, replay the stored terminal event and close.
    terminal = await _replay_terminal(redis, run_id)
    if terminal is not None:
        yield _sse(terminal)
        return

    async for event in _events(redis, run_id, pubsub, heartbeat):
        if event is None:
            yield b": ping\n\n"
            continue
        yield _sse(event)
        heartbeat.reset()
        if event.get("type") in TERMINAL_TYPES:
            return


async def sse_stream(
    redis: Redis, run_id: UUID | str, heartbeat_seconds: int
) -> AsyncIterator[bytes]:
    """Forward a run's events as SSE frames, replaying the terminal for late subscribers."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(run_channel(run_id))
    try:
        async for frame in _frames(redis, run_id, pubsub, Keepalive(heartbeat_seconds)):
            yield frame
    finally:
        await pubsub.unsubscribe(run_channel(run_id))
        await pubsub.aclose()
