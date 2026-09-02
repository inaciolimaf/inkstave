"""Unit tests for the Redis bridge envelope + cross-instance relay (spec 29)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis as fakeredis

from inkstave.collab.ws.redis_bridge import RedisBridge, decode_envelope, encode_envelope
from inkstave.collab.ws.rooms import Connection, RoomManager
from inkstave.collab.ydocument import YDocument


def test_envelope_round_trip() -> None:
    envelope = encode_envelope("inst-1", "conn-9", b"\x00\x01payload")
    assert decode_envelope(envelope) == ("inst-1", "conn-9", b"\x00\x01payload")


async def test_cross_instance_relay_and_origin_exclusion() -> None:
    server = fakeredis.FakeServer()
    redis_a = fakeredis.FakeRedis(server=server)
    redis_b = fakeredis.FakeRedis(server=server)
    bridge_a = RedisBridge(redis_a, "A", "collab:doc:")
    bridge_b = RedisBridge(redis_b, "B", "collab:doc:")
    doc = uuid4()

    seen_a: list[tuple[bytes, str | None]] = []
    seen_b: list[tuple[bytes, str | None]] = []

    async def on_a(payload: bytes, exclude: str | None) -> None:
        seen_a.append((payload, exclude))

    async def on_b(payload: bytes, exclude: str | None) -> None:
        seen_b.append((payload, exclude))

    sub_a = await bridge_a.subscribe(doc, on_a)
    sub_b = await bridge_b.subscribe(doc, on_b)
    await asyncio.sleep(0.05)

    await bridge_a.publish(doc, "connA", b"hello")
    await asyncio.sleep(0.05)

    # Instance B (different) delivers to everyone (exclude=None).
    assert (b"hello", None) in seen_b
    # Instance A (origin) excludes the sending connection on the local loopback.
    assert (b"hello", "connA") in seen_a

    await sub_a.aclose()
    await sub_b.aclose()
    await redis_a.aclose()
    await redis_b.aclose()


def _conn(conn_id: str, doc: UUID) -> Connection:
    return Connection(
        id=conn_id,
        user_id=uuid4(),
        document_id=doc,
        websocket=object(),
        send_queue=asyncio.Queue(),
    )


def _forwarder(rooms: RoomManager, doc: UUID) -> Any:
    """Relay a Redis payload into one instance's local room."""

    async def forward(payload: bytes, exclude: str | None) -> None:
        rooms.local_broadcast(doc, payload, exclude)

    return forward


async def _subscribe_both(
    bridge_a: RedisBridge,
    rooms_a: RoomManager,
    bridge_b: RedisBridge,
    rooms_b: RoomManager,
    doc: UUID,
) -> tuple[Any, Any]:
    """Attach both instances' forwarders and let the subscriptions settle."""
    sub_a = await bridge_a.subscribe(doc, _forwarder(rooms_a, doc))
    sub_b = await bridge_b.subscribe(doc, _forwarder(rooms_b, doc))
    await asyncio.sleep(0.05)
    return sub_a, sub_b


async def test_cross_instance_room_delivery() -> None:
    """Two instances + same Redis: a publish on A reaches a connection on B, the
    receiver *applies* the relayed update and converges, and A's own sending
    connection is not echoed (criterion 5)."""
    server = fakeredis.FakeServer()
    redis_a = fakeredis.FakeRedis(server=server)
    redis_b = fakeredis.FakeRedis(server=server)
    bridge_a = RedisBridge(redis_a, "A", "collab:doc:")
    bridge_b = RedisBridge(redis_b, "B", "collab:doc:")
    rooms_a = RoomManager()
    rooms_b = RoomManager()
    doc = uuid4()

    # Real Yjs docs on each side: the sender mutates its doc and the produced
    # update is what crosses the wire, so applying it on the receiver converges.
    sender_doc = YDocument()
    receiver_doc = YDocument()
    update = sender_doc.replace_text("hello, convergence\n")

    sender = _conn("connA", doc)
    receiver = _conn("connB", doc)
    rooms_a.join(sender)
    rooms_b.join(receiver)

    sub_a, sub_b = await _subscribe_both(bridge_a, rooms_a, bridge_b, rooms_b, doc)
    await bridge_a.publish(doc, "connA", update)
    await asyncio.sleep(0.05)

    relayed = receiver.send_queue.get_nowait()  # delivered cross-instance
    assert relayed == update  # raw bytes reach the receiver's queue unchanged
    assert sender.send_queue.empty()  # sender not echoed to itself

    # Criterion 5: the receiver applies the relayed update and converges.
    receiver_doc.apply_update(relayed)
    assert receiver_doc.text == sender_doc.text == "hello, convergence\n"

    await sub_a.aclose()
    await sub_b.aclose()
    await redis_a.aclose()
    await redis_b.aclose()
