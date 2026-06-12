"""Server-side refresh-token store backed by Redis.

Each refresh token has a ``refresh:{jti}`` record (TTL = refresh lifetime, so it
self-evicts) and belongs to a *family*. Rotation marks the old record ``rotated``
and presenting a rotated token is reuse — the whole family is revoked via a
``refresh_family_revoked:{family_id}`` marker that outlives its members.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.time import SYSTEM_CLOCK, Clock

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.config import Settings

_RECORD_PREFIX = "refresh:"
# Intentional, clearer rename of spec 07 §5.1's ``refresh_family:`` marker —
# identical semantics (marks an entire refresh lineage as revoked). Kept as-is
# rather than renamed live (renaming a deployed Redis key prefix is riskier than
# the nit it resolves); the divergence is recorded here as a decision.
_FAMILY_REVOKED_PREFIX = "refresh_family_revoked:"
# A per-user cutoff: any refresh token created at/before this instant is invalid.
# Used to sign out all of a user's sessions on a password change (spec 59).
_USER_REVOKED_AT_PREFIX = "refresh_user_revoked_at:"


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

    @staticmethod
    def _user_revoked_key(user_id: str) -> str:
        return f"{_USER_REVOKED_AT_PREFIX}{user_id}"

    async def store_refresh(
        self, *, jti: str, user_id: UUID, family_id: UUID, clock: Clock = SYSTEM_CLOCK
    ) -> None:
        """Persist a refresh record keyed by ``jti``.

        The record's expiry is derived from settings (``self._ttl``, the refresh
        lifetime) rather than passed in. This intentionally diverges from spec 07
        §5.3's ``store_refresh(jti, user_id, family_id, expires_at)`` signature so
        the TTL has a single source of truth (the Redis key TTL == the record's
        ``expires_at``); a caller-supplied ``expires_at`` would be redundant and
        could contradict the key TTL.
        """
        now = clock.now()
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

    async def revoke_user(self, user_id: UUID, *, clock: Clock = SYSTEM_CLOCK) -> None:
        """Invalidate every existing refresh token for a user (spec 59).

        Records the cutoff = now; any token created at/before it is rejected. The
        change-password flow uses this to sign out *all* sessions (including the
        actor's), who then re-authenticates. A token minted strictly after the
        cutoff would survive, but the current callers do not mint one.
        """
        await self._redis.set(
            self._user_revoked_key(str(user_id)), clock.now().isoformat(), ex=self._ttl
        )

    async def _user_revoked_at(self, user_id: str) -> datetime | None:
        raw = await self._redis.get(self._user_revoked_key(user_id))
        return (
            datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw) if raw else None
        )

    async def is_user_revoked(self, record: RefreshRecord) -> bool:
        """True if the record predates a per-user revocation cutoff (spec 59)."""
        cutoff = await self._user_revoked_at(record.user_id)
        return bool(cutoff and datetime.fromisoformat(record.created_at) <= cutoff)

    async def is_member_valid(self, jti: str) -> bool:
        record = await self.get_refresh(jti)
        if record is None or record.rotated:
            return False
        if await self.is_family_revoked(record.family_id):
            return False
        return not await self.is_user_revoked(record)


def build_refresh_store(redis: Redis, settings: Settings) -> RefreshStore:
    """Construct a :class:`RefreshStore` from a Redis client and settings."""
    return RefreshStore(redis, settings)
