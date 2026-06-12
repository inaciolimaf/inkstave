"""Redis connection provider.

A single asyncio Redis client/pool is created in the app lifespan and shared via
``app.state``; request code reaches it through the :func:`get_redis` dependency.
No pub/sub or job queue here — that arrives with the realtime/ARQ specs.
"""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis


async def create_redis_pool(url: str) -> Redis:
    """Create a pooled asyncio Redis client from a DSN.

    Does not connect eagerly; the first command (e.g. the lifespan ping)
    establishes a connection.
    """
    return Redis.from_url(url, decode_responses=False)


async def ping_redis(redis: Redis, timeout_seconds: float) -> bool:
    """Ping Redis, returning ``False`` on any error or timeout (never raising)."""
    try:
        async with asyncio.timeout(timeout_seconds):
            return bool(await redis.ping())
    except Exception:
        return False
