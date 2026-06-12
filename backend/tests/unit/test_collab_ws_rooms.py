"""Unit tests for the WS room manager, backpressure, and force-close (spec 29)."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from inkstave.collab.ws.rooms import (
    CLOSE_SLOW_CONSUMER,
    Connection,
    RoomManager,
)
from inkstave.collab.ws.router import _force_close, _make_forwarder


class _FakeWS:
    def __init__(self) -> None:
        self.closed: int | None = None

    async def close(self, code: int) -> None:
        self.closed = code


def _conn(document_id: UUID, conn_id: str = "c1", maxsize: int = 10) -> Connection:
    return Connection(
        id=conn_id,
        user_id=uuid4(),
        document_id=document_id,
        websocket=_FakeWS(),
        send_queue=asyncio.Queue(maxsize=maxsize),
    )


def test_join_leave_lifecycle() -> None:
    rooms = RoomManager()
    doc = uuid4()
    a, b = _conn(doc, "a"), _conn(doc, "b")

    _room, created = rooms.join(a)
    assert created is True
    _room2, created2 = rooms.join(b)
    assert created2 is False
    assert rooms.room_count() == 1

    assert rooms.leave(a) is False  # b still present
    assert rooms.leave(b) is True  # now empty -> removed
    assert rooms.is_empty(doc)
    assert rooms.room_count() == 0


def test_local_broadcast_excludes_sender() -> None:
    rooms = RoomManager()
    doc = uuid4()
    a, b = _conn(doc, "a"), _conn(doc, "b")
    rooms.join(a)
    rooms.join(b)

    overflowed = rooms.local_broadcast(doc, b"payload", exclude="a")
    assert overflowed == []
    assert a.send_queue.empty()
    assert b.send_queue.get_nowait() == b"payload"


def test_try_enqueue_overflow() -> None:
    conn = _conn(uuid4(), maxsize=2)
    assert conn.try_enqueue(b"1") is True
    assert conn.try_enqueue(b"2") is True
    assert conn.try_enqueue(b"3") is False  # queue full


def test_local_broadcast_reports_overflow() -> None:
    rooms = RoomManager()
    doc = uuid4()
    conn = _conn(doc, "a", maxsize=1)
    rooms.join(conn)
    rooms.local_broadcast(doc, b"1", None)  # fills the queue
    assert rooms.local_broadcast(doc, b"2", None) == [conn]


async def test_force_close_is_idempotent() -> None:
    conn = _conn(uuid4(), "a")
    await _force_close(conn, CLOSE_SLOW_CONSUMER)
    assert conn.websocket.closed == CLOSE_SLOW_CONSUMER  # type: ignore[attr-defined]
    assert conn.closed is True
    conn.websocket.closed = None  # type: ignore[attr-defined]
    await _force_close(conn, CLOSE_SLOW_CONSUMER)  # already closed -> no-op
    assert conn.websocket.closed is None  # type: ignore[attr-defined]


async def test_enqueue_timed_succeeds_within_grace_window() -> None:
    # spec 68 #108: a momentarily-full queue that drains within the grace window
    # is enqueued (no false-positive slow-consumer eviction).
    conn = _conn(uuid4(), maxsize=1)
    conn.try_enqueue(b"fill")  # queue now full

    async def drain() -> None:
        await asyncio.sleep(0)
        conn.send_queue.get_nowait()  # make room so the timed put can complete

    asyncio.create_task(drain())  # noqa: RUF006
    assert await conn.enqueue_timed(b"payload", timeout_ms=200) is True


async def test_enqueue_timed_times_out_on_full_queue() -> None:
    # spec 68 #108: a queue that never drains within the timeout reports the socket
    # as a slow consumer (caller closes it with 4408).
    conn = _conn(uuid4(), maxsize=1)
    conn.try_enqueue(b"fill")  # queue stays full
    assert await conn.enqueue_timed(b"payload", timeout_ms=20) is False


async def test_broadcast_timed_consumes_setting_and_reports_overflow() -> None:
    # spec 68 #108: the configured COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS is actually
    # consumed — local_broadcast_timed waits that long before declaring overflow,
    # then the transport closes the socket with CLOSE_SLOW_CONSUMER (4408).
    rooms = RoomManager(slow_client_timeout_ms=20)
    doc = uuid4()
    slow = _conn(doc, "slow", maxsize=1)
    rooms.join(slow)
    slow.try_enqueue(b"fill")  # slow consumer's queue is full and never drains

    overflowed = await rooms.local_broadcast_timed(doc, b"payload", exclude=None)
    assert overflowed == [slow]

    await _force_close(overflowed[0], CLOSE_SLOW_CONSUMER)
    assert slow.websocket.closed == CLOSE_SLOW_CONSUMER  # type: ignore[attr-defined]


async def test_forwarder_closes_slow_consumer_without_stalling_others() -> None:
    class _Components:
        rooms = RoomManager()

    components = _Components()
    doc = uuid4()
    slow = _conn(doc, "slow", maxsize=1)
    healthy = _conn(doc, "healthy", maxsize=10)
    components.rooms.join(slow)
    components.rooms.join(healthy)
    slow.try_enqueue(b"fill")  # slow consumer's queue is now full

    forwarder = _make_forwarder(components, doc)  # type: ignore[arg-type]
    await forwarder(b"broadcast", None)
    await asyncio.sleep(0.02)  # let the scheduled close run

    assert slow.websocket.closed == CLOSE_SLOW_CONSUMER  # type: ignore[attr-defined]
    assert healthy.send_queue.get_nowait() == b"broadcast"  # healthy member still served
