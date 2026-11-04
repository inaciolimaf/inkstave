"""The per-project Git lock, shared by every backend replica through Redis (spec 121).

``SET NX PX`` takes it, with the operation's deadline as its expiry, so a crashed holder cannot block a
project for longer than one operation. Waiting for it has the same deadline.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from inkstave.core.errors import ConflictError

if TYPE_CHECKING:
    from redis.asyncio import Redis

_POLL_SECONDS = 0.05


class GitBusyError(ConflictError):
    error_type = "git_busy"

    def __init__(self) -> None:
        super().__init__("Another Git operation on this project is still running. Try again shortly.")


def lock_key(project_id: UUID) -> str:
    return f"git:lock:{project_id}"


@asynccontextmanager
async def project_git_lock(redis: Redis, project_id: UUID, timeout_s: float) -> AsyncIterator[None]:
    key = lock_key(project_id)
    token = uuid4().hex
    expiry_ms = max(1, int(timeout_s * 1000))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not await redis.set(key, token, nx=True, px=expiry_ms):
        if loop.time() >= deadline:
            raise GitBusyError()
        await asyncio.sleep(_POLL_SECONDS)
    try:
        yield
    finally:
        holder = await redis.get(key)
        if holder is not None and holder.decode("ascii") == token:
            await redis.delete(key)
