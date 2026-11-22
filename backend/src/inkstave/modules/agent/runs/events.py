"""Agent run event bus (spec 44): Redis channels, sinks, and cancellation.

Events are JSON objects ``{type, run_id, seq, ts, ...payload}`` published to the
per-run Redis channel and forwarded over SSE. ``seq`` is a per-run monotonic counter
for client ordering/dedup. A short-lived "last event" key lets late subscribers
replay the terminal event.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from redis.asyncio import Redis

# Event type names (clients must ignore unknown types — forward compatibility).
TERMINAL_TYPES = frozenset({"done", "error"})


def run_channel(run_id: UUID | str) -> str:
    return f"agent:run:{run_id}"


def cancel_key(run_id: UUID | str) -> str:
    return f"agent:cancel:{run_id}"


def last_event_key(run_id: UUID | str) -> str:
    return f"agent:run:{run_id}:last"


def beat_key(run_id: UUID | str) -> str:
    """Progress marker of a run: it expires when the run has been silent for the stall timeout."""
    return f"agent:run:{run_id}:beat"


async def record_progress(redis: Redis, run_id: UUID | str, stall_seconds: int) -> None:
    await redis.set(beat_key(run_id), b"1", ex=stall_seconds)


def build_event(run_id: str, seq: int, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": event_type,
        "run_id": run_id,
        "seq": seq,
        "ts": datetime.now(UTC).isoformat(),
        **payload,
    }


class EventSink(Protocol):
    run_id: str

    async def emit(self, event_type: str, **payload: Any) -> dict[str, Any]: ...


class InMemoryEventSink:
    """Collects events in a list — the test-friendly sink (no Redis)."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[dict[str, Any]] = []
        self._seq = 0

    async def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = build_event(self.run_id, self._seq, event_type, payload)
        self._seq += 1
        self.events.append(event)
        return event


class RedisEventSink:
    """Publishes events to the per-run Redis channel; persists the terminal event.

    Every event also refreshes the run's progress marker when ``stall_seconds`` is set, so the
    reaper can tell a live run from one whose worker died (spec 44).
    """

    def __init__(self, redis: Redis, run_id: str, ttl_seconds: int, stall_seconds: int | None = None) -> None:
        self.run_id = run_id
        self._redis = redis
        self._ttl = ttl_seconds
        self._stall = stall_seconds
        self._seq = 0

    async def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = build_event(self.run_id, self._seq, event_type, payload)
        self._seq += 1
        data = json.dumps(event, default=str).encode()
        if self._stall:
            await record_progress(self._redis, self.run_id, self._stall)
        await self._redis.publish(run_channel(self.run_id), data)
        if event_type in TERMINAL_TYPES:
            # Let a late subscriber replay the terminal event.
            await self._redis.set(last_event_key(self.run_id), data, ex=self._ttl)
        return event


async def request_cancel(redis: Redis, run_id: UUID | str, ttl_seconds: int) -> None:
    await redis.set(cancel_key(run_id), b"1", ex=ttl_seconds)


async def is_cancel_requested(redis: Redis, run_id: UUID | str) -> bool:
    return bool(await redis.exists(cancel_key(run_id)))
