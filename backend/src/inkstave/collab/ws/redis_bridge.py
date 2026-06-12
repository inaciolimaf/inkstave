"""Redis pub/sub fan-out so clients on different app instances share a room (spec 29).

One channel per document (``{prefix}{document_id}``). Each relayed payload is
wrapped in a small binary envelope identifying the origin **instance** and
**connection** so the originating instance does not echo back to the sender. The
payload is the raw Yjs y-protocols message; the envelope is length-framed and
never seen by browsers.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import UUID

from pycrdt import Decoder, write_message

if TYPE_CHECKING:
    from redis.asyncio import Redis

# (payload, exclude_connection_id) — exclude is set only on the origin instance.
OnMessage = Callable[[bytes, str | None], Awaitable[None]]


def encode_envelope(instance_id: str, origin_conn_id: str, payload: bytes) -> bytes:
    return (
        write_message(instance_id.encode())
        + write_message(origin_conn_id.encode())
        + write_message(payload)
    )


def decode_envelope(data: bytes) -> tuple[str, str, bytes]:
    decoder = Decoder(data)
    instance_id = (decoder.read_message() or b"").decode()
    origin_conn_id = (decoder.read_message() or b"").decode()
    payload = decoder.read_message() or b""
    return instance_id, origin_conn_id, payload


class Subscription:
    def __init__(self, pubsub: object, task: asyncio.Task[None]) -> None:
        self._pubsub = pubsub
        self._task = task

    async def aclose(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        with contextlib.suppress(Exception):
            await self._pubsub.unsubscribe()  # type: ignore[attr-defined]
            await self._pubsub.aclose()  # type: ignore[attr-defined]


class RedisBridge:
    def __init__(self, redis: Redis, instance_id: str, channel_prefix: str) -> None:
        self._redis = redis
        self._instance_id = instance_id
        self._prefix = channel_prefix

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def channel(self, document_id: UUID) -> str:
        return f"{self._prefix}{document_id}"

    async def publish(self, document_id: UUID, origin_conn_id: str, payload: bytes) -> None:
        envelope = encode_envelope(self._instance_id, origin_conn_id, payload)
        await self._redis.publish(self.channel(document_id), envelope)

    async def subscribe(self, document_id: UUID, on_message: OnMessage) -> Subscription:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self.channel(document_id))
        task = asyncio.create_task(self._reader(pubsub, on_message))
        return Subscription(pubsub, task)

    async def _reader(self, pubsub: object, on_message: OnMessage) -> None:
        async for message in pubsub.listen():  # type: ignore[attr-defined]
            if message.get("type") != "message":
                continue
            data = message["data"]
            if not isinstance(data, bytes | bytearray):
                continue
            instance_id, origin_conn_id, payload = decode_envelope(bytes(data))
            # Only exclude the sender on its *own* instance (local loopback).
            exclude = origin_conn_id if instance_id == self._instance_id else None
            await on_message(payload, exclude)
