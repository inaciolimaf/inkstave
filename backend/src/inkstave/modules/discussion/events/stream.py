"""The project event stream: SSE frames fed by Redis pub/sub (spec 117).

One connection per open project. Frames carry ``id:`` so the browser can send ``Last-Event-ID``
on reconnect, but the server does not replay: a client that reconnects refetches the latest
page of what it shows. Membership is re-checked at every keep-alive, so a removed member's
stream ends within one interval.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.core.http.sse import Keepalive, event_pump
from inkstave.infra.redis import close_pubsub
from inkstave.modules.discussion.events.channel import project_channel

if TYPE_CHECKING:
    from redis.asyncio import Redis

# Answers whether the caller still holds an active membership of the project.
MemberCheck = Callable[[], Awaitable[bool]]

_POLL_SECONDS = 0.1


def _frame(event: dict[str, Any]) -> bytes:
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n".encode()


async def _frames(pubsub: Any, is_member: MemberCheck, keepalive_seconds: float) -> AsyncIterator[bytes]:
    recheck = Keepalive(keepalive_seconds)  # membership cadence, whatever the traffic
    idle = Keepalive(keepalive_seconds)  # keep-alive comments only when nothing else was sent
    async for event in event_pump(pubsub, poll=min(_POLL_SECONDS, keepalive_seconds)):
        if recheck.due() and not await is_member():
            return
        if event is None:
            if idle.due():
                yield b": keep-alive\n\n"
            continue
        yield _frame(event)
        idle.reset()


async def project_events_stream(
    redis: Redis, project_id: UUID, is_member: MemberCheck, keepalive_seconds: float
) -> AsyncIterator[bytes]:
    """Yield SSE frames for one project until the caller's membership ends or the client leaves."""
    channel = project_channel(project_id)
    pubsub = redis.pubsub()
    # Subscribe before the first frame so nothing published after the request is lost.
    await pubsub.subscribe(channel)
    try:
        yield b": connected\n\n"
        async for frame in _frames(pubsub, is_member, keepalive_seconds):
            yield frame
    finally:
        await pubsub.unsubscribe(channel)
        await close_pubsub(pubsub)
