"""Redis connection provider.

A single asyncio Redis client/pool is created in the app lifespan and shared via
``app.state``; request code reaches it through the :func:`get_redis` dependency.
No pub/sub or job queue here — that arrives with the realtime/ARQ specs.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from redis.asyncio import Redis

if TYPE_CHECKING:
    from redis.asyncio.client import PubSub


async def create_redis_pool(url: str, *, connect_timeout_s: float, socket_timeout_s: float) -> Redis:
    """Create a pooled asyncio Redis client from a DSN.

    Does not connect eagerly; the first command (e.g. the lifespan ping)
    establishes a connection.
    """
    client: Redis = Redis.from_url(
        url,
        decode_responses=False,
        socket_connect_timeout=connect_timeout_s,
        socket_timeout=socket_timeout_s,
    )
    return client


async def close_pubsub(pubsub: PubSub) -> None:
    """Close a pub/sub connection."""
    # redis-py's stubs leave PubSub.aclose unannotated, and it has no typed alternative.
    await pubsub.aclose()  # type: ignore[no-untyped-call]


async def ping_redis(redis: Redis, timeout_seconds: float) -> bool:
    """Ping Redis, returning ``False`` on any error or timeout (never raising)."""
    try:
        async with asyncio.timeout(timeout_seconds):
            return bool(await redis.ping())
    except Exception:
        return False
