"""Redis pub/sub + SSE serialisation for live project-import status (spec 101).

Parallels :mod:`inkstave.compile.stream` (spec 22) but over the import status
enum (which has a distinct terminal set, including ``partial``). One channel per
import id; the job publishes a status payload on every transition.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.db.models.project_import import ProjectImportStatus, is_terminal
from inkstave.sse import Keepalive, event_pump

if TYPE_CHECKING:
    from redis.asyncio import Redis


def events_channel(import_id: UUID) -> str:
    return f"project_import:events:{import_id}"


async def publish_status(redis: Redis, import_id: UUID, payload: dict[str, Any]) -> None:
    await redis.publish(events_channel(import_id), json.dumps(payload, default=str).encode())


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


SnapshotProvider = Callable[[], Awaitable[dict[str, Any] | None]]


def _is_terminal(payload: dict[str, Any]) -> bool:
    return is_terminal(ProjectImportStatus(payload["status"]))


async def _frames(
    pubsub: Any, initial: dict[str, Any], keepalive_seconds: int
) -> AsyncIterator[bytes]:
    """The snapshot frame, then one frame per transition / keep-alive until terminal."""
    yield _sse("status", initial)
    if _is_terminal(initial):
        return

    keepalive = Keepalive(keepalive_seconds)
    async for payload in event_pump(pubsub, poll=min(0.1, float(keepalive_seconds))):
        if payload is None:
            if keepalive.due():
                yield b": keep-alive\n\n"
            continue
        yield _sse("status", payload)
        keepalive.reset()
        if _is_terminal(payload):
            return


async def sse_stream(
    redis: Redis,
    import_id: UUID,
    snapshot: SnapshotProvider,
    keepalive_seconds: int,
) -> AsyncIterator[bytes]:
    """Yield SSE frames: an initial snapshot, one per transition, keep-alives, then close."""
    initial = await snapshot()
    if initial is None:
        return

    # Subscribe BEFORE yielding the snapshot so no transition published between
    # the snapshot read and the subscribe is lost.
    pubsub = redis.pubsub()
    await pubsub.subscribe(events_channel(import_id))
    try:
        async for frame in _frames(pubsub, initial, keepalive_seconds):
            yield frame
    finally:
        await pubsub.unsubscribe(events_channel(import_id))
        await pubsub.aclose()
