"""Unit tests for the WS message dispatch wiring with a mocked manager (spec 29)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from inkstave.collab.protocol import (
    SyncUpdate,
    encode_awareness,
    encode_sync_step1,
    encode_update,
    read_message,
)
from inkstave.collab.ws.components import CollabWsSettings
from inkstave.collab.ws.rooms import Connection
from inkstave.collab.ws.router import _dispatch


class _FakeWS:
    def __init__(self) -> None:
        self.closed: int | None = None

    async def close(self, code: int) -> None:
        self.closed = code


class _FakeManager:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def handle_sync_step1(self, doc: Any, sv: bytes) -> tuple[bytes, bytes]:
        self.calls.append(("step1", sv))
        return b"STEP2", b"STEP1"

    async def handle_update(self, doc: Any, update: bytes, origin: str | None) -> bytes:
        self.calls.append(("update", update, origin))
        return update

    async def handle_awareness(self, doc: Any, update: bytes) -> bytes:
        self.calls.append(("awareness", update))
        return update


class _FakeBridge:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, doc: Any, conn_id: str, payload: bytes) -> None:
        self.published.append((conn_id, payload))


class _Components:
    def __init__(self) -> None:
        self.manager = _FakeManager()
        self.redis_bridge = _FakeBridge()
        self.history = None


def _ws_settings(max_update: int = 1_000_000) -> CollabWsSettings:
    return CollabWsSettings(
        max_frame_bytes=1_000_000,
        send_queue_max=10,
        slow_client_timeout_ms=2000,
        max_msgs_per_sec=200,
        ping_interval_seconds=25.0,
        pong_timeout_seconds=10.0,
        channel_prefix="c:",
        max_update_bytes=max_update,
    )


def _conn() -> Connection:
    return Connection(
        id="c1",
        user_id=uuid4(),
        document_id=uuid4(),
        websocket=_FakeWS(),
        send_queue=asyncio.Queue(maxsize=10),
    )


async def test_sync_step1_enqueues_both_replies() -> None:
    comp, conn = _Components(), _conn()
    cont = await _dispatch(read_message(encode_sync_step1(b"\x00")), conn, comp, _ws_settings())  # type: ignore[arg-type]
    assert cont is True
    assert comp.manager.calls[0][0] == "step1"
    assert conn.send_queue.get_nowait() == b"STEP2"
    assert conn.send_queue.get_nowait() == b"STEP1"


async def test_update_routes_to_manager_and_publishes() -> None:
    comp, conn = _Components(), _conn()
    update = b"\x07yjs-update"
    cont = await _dispatch(read_message(encode_update(update)), conn, comp, _ws_settings())  # type: ignore[arg-type]
    assert cont is True
    assert comp.manager.calls[0] == ("update", update, "c1")
    assert comp.redis_bridge.published == [("c1", encode_update(update))]


async def test_awareness_routes_to_manager_and_publishes() -> None:
    comp, conn = _Components(), _conn()
    blob = b"\x01\x02"
    await _dispatch(read_message(encode_awareness(blob)), conn, comp, _ws_settings())  # type: ignore[arg-type]
    assert comp.manager.calls[0] == ("awareness", blob)
    assert comp.redis_bridge.published == [("c1", encode_awareness(blob))]


async def test_oversize_update_closes_4400() -> None:
    comp, conn = _Components(), _conn()
    parsed = read_message(encode_update(b"x" * 50))
    assert isinstance(parsed, SyncUpdate)
    cont = await _dispatch(parsed, conn, comp, _ws_settings(max_update=5))  # type: ignore[arg-type]
    assert cont is False
    assert conn.websocket.closed == 4400  # type: ignore[attr-defined]
    assert comp.manager.calls == []  # never reached the manager


async def test_unknown_message_is_ignored() -> None:
    from pycrdt import write_var_uint

    comp, conn = _Components(), _conn()
    cont = await _dispatch(read_message(write_var_uint(9)), conn, comp, _ws_settings())  # type: ignore[arg-type]
    assert cont is True
    assert comp.manager.calls == []
    assert comp.redis_bridge.published == []
