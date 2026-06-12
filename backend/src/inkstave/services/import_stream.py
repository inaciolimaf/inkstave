"""Redis pub/sub + SSE serialisation for live project-import status (spec 101).

Parallels :mod:`inkstave.compile.stream` (spec 22) but over the import status
enum (which has a distinct terminal set, including ``partial``). One channel per
import id; the job publishes a status payload on every transition.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.db.models.project_import import ProjectImportStatus, is_terminal

if TYPE_CHECKING:
    from redis.asyncio import Redis


def events_channel(import_id: UUID) -> str:
    return f"project_import:events:{import_id}"


async def publish_status(redis: Redis, import_id: UUID, payload: dict[str, Any]) -> None:
    await redis.publish(events_channel(import_id), json.dumps(payload, default=str).encode())


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


SnapshotProvider = Callable[[], Awaitable[dict[str, Any] | None]]


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

    pubsub = redis.pubsub()
    await pubsub.subscribe(events_channel(import_id))
    poll = min(0.1, float(keepalive_seconds))
    last = time.monotonic()
    try:
        yield _sse("status", initial)
        if is_terminal(ProjectImportStatus(initial["status"])):
            return
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll)
            if message is None:
                if time.monotonic() - last >= keepalive_seconds:
                    yield b": keep-alive\n\n"
                    last = time.monotonic()
                continue
            payload = json.loads(message["data"])
            yield _sse("status", payload)
            last = time.monotonic()
            if is_terminal(ProjectImportStatus(payload["status"])):
                return
    finally:
        await pubsub.unsubscribe(events_channel(import_id))
        await pubsub.aclose()
