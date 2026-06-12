"""Small, explicit Redis cache for hot reads (spec 53 §5.5). Conservative + fail-soft.

Only post-authz, cache-safe data is cached, keyed by resource id, with a short TTL and
**explicit invalidation** on the corresponding write. A cache miss/backends error always
falls through to the source of truth — correctness over hit rate.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.config import Settings

logger = logging.getLogger("inkstave.cache")


def project_meta_key(project_id: UUID) -> str:
    return f"cache:project:{project_id}"


class RedisCache:
    """JSON get/set with TTL + explicit invalidation; disabled mode bypasses entirely."""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._enabled = settings.cache_enabled
        self._ttl = settings.cache_ttl_seconds

    async def get_json(self, key: str) -> Any | None:
        if not self._enabled:
            return None
        try:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:  # fail soft → caller reads the source of truth
            logger.warning("cache get failed (%s): %s", key, exc)
            return None

    async def set_json(self, key: str, value: Any) -> None:
        if not self._enabled:
            return
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=self._ttl)
        except Exception as exc:
            logger.warning("cache set failed (%s): %s", key, exc)

    async def invalidate(self, *keys: str) -> None:
        if not keys:
            return
        try:
            await self._redis.delete(*keys)
        except Exception as exc:
            logger.warning("cache invalidate failed (%s): %s", keys, exc)
