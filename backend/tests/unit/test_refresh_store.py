"""Unit tests for the Redis-backed refresh-token store (fakeredis)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from inkstave.auth.refresh_store import build_refresh_store
from inkstave.config import get_settings


def _store(redis: Any) -> Any:
    return build_refresh_store(redis, get_settings())


async def test_store_and_get(redis: Any) -> None:
    store = _store(redis)
    jti, user_id, family_id = "jti-1", uuid4(), uuid4()
    await store.store_refresh(jti, user_id, family_id)

    record = await store.get_refresh(jti)
    assert record is not None
    assert record.user_id == str(user_id)
    assert record.family_id == str(family_id)
    assert record.rotated is False
    assert await store.get_refresh("missing") is None


async def test_rotate_marks_used(redis: Any) -> None:
    store = _store(redis)
    jti, family_id = "jti-2", uuid4()
    await store.store_refresh(jti, uuid4(), family_id)
    assert await store.is_member_valid(jti) is True

    await store.rotate_refresh(jti)
    record = await store.get_refresh(jti)
    assert record is not None and record.rotated is True
    assert await store.is_member_valid(jti) is False


async def test_rotate_missing_jti_is_noop(redis: Any) -> None:
    store = _store(redis)
    await store.rotate_refresh("does-not-exist")  # must not raise
    assert await store.get_refresh("does-not-exist") is None


async def test_revoke_family_invalidates_members(redis: Any) -> None:
    store = _store(redis)
    family_id = uuid4()
    await store.store_refresh("jti-3", uuid4(), family_id)
    assert await store.is_member_valid("jti-3") is True

    await store.revoke_family(str(family_id))
    assert await store.is_family_revoked(str(family_id)) is True
    assert await store.is_member_valid("jti-3") is False
