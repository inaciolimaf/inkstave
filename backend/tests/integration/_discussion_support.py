"""Shared helpers for the project chat and event stream tests (spec 117).

Not ``test_``-prefixed, so pytest does not collect it. Every wait here has a deadline.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

from httpx import AsyncClient

from inkstave.modules.discussion.events.channel import project_channel

DEADLINE_S = 2.0
PROJECTS = "/api/v1/projects"


def chat_url(project_id: str) -> str:
    return f"{PROJECTS}/{project_id}/chat"


async def post_message(client: AsyncClient, headers: dict[str, str], project_id: str, body: str) -> Any:
    return await client.post(f"{chat_url(project_id)}/messages", json={"body": body}, headers=headers)


async def subscribe(redis: Any, project_id: UUID) -> Any:
    pubsub = redis.pubsub()
    await pubsub.subscribe(project_channel(project_id))
    return pubsub


async def next_event(pubsub: Any, deadline: float = DEADLINE_S) -> dict[str, Any]:
    """The next JSON event on a subscribed channel, or a failed assertion at the deadline."""

    async def poll() -> dict[str, Any]:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.05)
            if message is not None:
                loaded: dict[str, Any] = json.loads(message["data"])
                return loaded

    return await asyncio.wait_for(poll(), deadline)


async def no_event(pubsub: Any, polls: int = 3) -> bool:
    """True when nothing arrives within a few short polls."""
    for _ in range(polls):
        if await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.02) is not None:
            return False
    return True


async def read_frames_until(
    frames: AsyncIterator[bytes], marker: bytes, deadline: float = DEADLINE_S
) -> list[bytes]:
    """Consume SSE frames until one contains ``marker``; returns everything read, marker frame last."""
    seen: list[bytes] = []

    async def consume() -> None:
        async for frame in frames:
            seen.append(frame)
            if marker in frame:
                return

    await asyncio.wait_for(consume(), deadline)
    return seen


def failing_commit_session(db_session: Any) -> Callable[..., AsyncIterator[Any]]:
    """A unit-of-work dependency whose commit fails after the route has run."""

    async def override() -> AsyncIterator[Any]:
        yield db_session
        raise RuntimeError("commit failed")

    return override
