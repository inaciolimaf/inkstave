"""Redis pub/sub channels + SSE serialisation for live compile status (spec 22)."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.db.models.compile import CompileJobStatus, is_terminal

if TYPE_CHECKING:
    from redis.asyncio import Redis


def events_channel(compile_id: UUID) -> str:
    return f"compile:events:{compile_id}"


def cancel_key(compile_id: UUID) -> str:
    return f"compile:cancel:{compile_id}"


async def publish_status(redis: Redis, compile_id: UUID, payload: dict[str, Any]) -> None:
    await redis.publish(events_channel(compile_id), json.dumps(payload, default=str).encode())


async def request_cancel(redis: Redis, compile_id: UUID, ttl_seconds: int) -> None:
    """Set the cancel flag (short TTL) and notify any running worker."""
    await redis.set(cancel_key(compile_id), b"1", ex=ttl_seconds)
    await redis.publish(cancel_key(compile_id), b"1")


async def is_cancel_requested(redis: Redis, compile_id: UUID) -> bool:
    return bool(await redis.exists(cancel_key(compile_id)))


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


SnapshotProvider = Callable[[], Awaitable[dict[str, Any] | None]]


async def sse_stream(
    redis: Redis,
    compile_id: UUID,
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
    await pubsub.subscribe(events_channel(compile_id))
    poll = min(0.1, float(keepalive_seconds))
    last = time.monotonic()
    try:
        yield _sse("status", initial)
        if is_terminal(CompileJobStatus(initial["status"])):
            return
        while True:
            # A short poll (so transient None acks don't masquerade as keep-alives);
            # emit a real keep-alive only once the configured interval has elapsed.
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll)
            if message is None:
                if time.monotonic() - last >= keepalive_seconds:
                    yield b": keep-alive\n\n"
                    last = time.monotonic()
                continue
            payload = json.loads(message["data"])
            yield _sse("status", payload)
            last = time.monotonic()
            if is_terminal(CompileJobStatus(payload["status"])):
                return
    finally:
        await pubsub.unsubscribe(events_channel(compile_id))
        await pubsub.aclose()
