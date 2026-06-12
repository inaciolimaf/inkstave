"""Server-side refresh-token store backed by Redis.

Each refresh token has a ``refresh:{jti}`` record (TTL = refresh lifetime, so it
self-evicts) and belongs to a *family*. Rotation marks the old record ``rotated``
and presenting a rotated token is reuse — the whole family is revoked via a
``refresh_family_revoked:{family_id}`` marker that outlives its members.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.config import Settings

_RECORD_PREFIX = "refresh:"
_FAMILY_REVOKED_PREFIX = "refresh_family_revoked:"


@dataclass(frozen=True)
class RefreshRecord:
    user_id: str
    family_id: str
    rotated: bool
    created_at: str
    expires_at: str


class RefreshStore:
    """Stores, rotates and revokes refresh tokens in Redis."""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._ttl = settings.refresh_token_ttl_seconds

    @staticmethod
    def _record_key(jti: str) -> str:
        return f"{_RECORD_PREFIX}{jti}"

    @staticmethod
    def _family_key(family_id: str) -> str:
        return f"{_FAMILY_REVOKED_PREFIX}{family_id}"

    async def store_refresh(self, jti: str, user_id: UUID, family_id: UUID) -> None:
        now = datetime.now(UTC)
        record = {
            "user_id": str(user_id),
            "family_id": str(family_id),
            "rotated": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self._ttl)).isoformat(),
        }
        await self._redis.set(self._record_key(jti), json.dumps(record), ex=self._ttl)

    async def get_refresh(self, jti: str) -> RefreshRecord | None:
        raw = await self._redis.get(self._record_key(jti))
        if raw is None:
            return None
        data = json.loads(raw)
        return RefreshRecord(**data)

    async def rotate_refresh(self, jti: str) -> None:
        """Mark a refresh record as used, preserving its remaining TTL."""
        key = self._record_key(jti)
        raw = await self._redis.get(key)
        if raw is None:
            return
        data = json.loads(raw)
        data["rotated"] = True
        ttl = await self._redis.ttl(key)
        await self._redis.set(key, json.dumps(data), ex=ttl if ttl and ttl > 0 else self._ttl)

    async def revoke_family(self, family_id: str) -> None:
        await self._redis.set(self._family_key(family_id), b"1", ex=self._ttl)

    async def is_family_revoked(self, family_id: str) -> bool:
        return bool(await self._redis.exists(self._family_key(family_id)))

    async def is_member_valid(self, jti: str) -> bool:
        record = await self.get_refresh(jti)
        if record is None or record.rotated:
            return False
        return not await self.is_family_revoked(record.family_id)


def build_refresh_store(redis: Redis, settings: Settings) -> RefreshStore:
    """Construct a :class:`RefreshStore` from a Redis client and settings."""
    return RefreshStore(redis, settings)
