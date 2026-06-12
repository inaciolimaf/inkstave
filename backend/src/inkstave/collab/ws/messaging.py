"""Inbound-message handling for the collab WebSocket (spec 29).

Per-connection rate guard, frame validation, and the dispatch that routes one
parsed Yjs message to the spec-28 ``DocumentManager`` + Redis fan-out. Kept
separate from the connection lifecycle so the public ``router`` module stays a
thin transport surface.
"""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING

from pycrdt import Decoder

from inkstave.collab.manager import UpdateTooLarge
from inkstave.collab.protocol import (
    AwarenessMessage,
    SyncStep1,
    SyncStep2,
    SyncUpdate,
    encode_awareness,
    encode_update,
    read_message,
)
from inkstave.collab.ws.connection import _force_close
from inkstave.collab.ws.rooms import (
    CLOSE_BAD_MESSAGE,
    CLOSE_RATE_LIMITED,
    Connection,
)

if TYPE_CHECKING:
    from inkstave.collab.ws.components import CollabComponents, CollabWsSettings


class _RateLimiter:
    """A simple per-connection 1-second sliding-window rate guard."""

    def __init__(self, max_per_sec: int) -> None:
        self._max = max_per_sec
        self._count = 0
        self._window = monotonic()

    def allow(self) -> bool:
        now = monotonic()
        if now - self._window >= 1.0:
            self._window = now
            self._count = 0
        self._count += 1
        return self._count <= self._max


def _first_awareness_client(update: bytes) -> int | None:
    try:
        decoder = Decoder(update)
        if decoder.read_var_uint() == 0:
            return None
        return decoder.read_var_uint()
    except Exception:
        return None


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _dispatch(
    parsed: object, conn: Connection, components: CollabComponents, ws: CollabWsSettings
) -> bool:
    """Route one inbound message to the manager + Redis. Returns False to stop."""
    doc_id = conn.document_id
    if isinstance(parsed, SyncStep1):
        step2, server_step1 = await components.manager.handle_sync_step1(
            doc_id, parsed.state_vector
        )
        conn.try_enqueue(step2)
        # Spec 29 §5.2.1: send our SyncStep1 "if not already". The handshake
        # already enqueued the server's step1 once, so skip the duplicate here.
        if not getattr(conn, "server_step1_sent", False):
            conn.try_enqueue(server_step1)
            conn.server_step1_sent = True  # type: ignore[attr-defined]
    elif isinstance(parsed, SyncStep2 | SyncUpdate):
        if not conn.can_write:
            # Viewer (spec 34): drop the update — never apply, persist, or broadcast.
            # The viewer still receives others' edits + awareness.
            return True
        if len(parsed.update) > ws.max_update_bytes:
            await _force_close(conn, CLOSE_BAD_MESSAGE)
            return False
        try:
            relayable = await components.manager.handle_update(
                doc_id, parsed.update, origin=conn.id
            )
        except UpdateTooLarge:
            await _force_close(conn, CLOSE_BAD_MESSAGE)
            return False
        await components.redis_bridge.publish(doc_id, conn.id, encode_update(relayable))
        # Observe the applied update into version history (spec 36); non-blocking.
        if components.history is not None and conn.project_id is not None:
            await components.history.capture_update(
                project_id=conn.project_id,
                doc_id=doc_id,
                update=parsed.update,
                author_id=conn.user_id,
                at=_utcnow(),
            )
    elif isinstance(parsed, AwarenessMessage):
        if conn.awareness_client_id is None:
            conn.awareness_client_id = _first_awareness_client(parsed.update)
        relayable = await components.manager.handle_awareness(doc_id, parsed.update)
        await components.redis_bridge.publish(doc_id, conn.id, encode_awareness(relayable))
    # UnknownMessage and anything else: ignore.
    return True


async def _receive_loop(
    conn: Connection, components: CollabComponents, ws: CollabWsSettings
) -> None:
    limiter = _RateLimiter(ws.max_msgs_per_sec)
    websocket = conn.websocket
    while not conn.closed:
        message = await websocket.receive()  # type: ignore[attr-defined]
        if message["type"] == "websocket.disconnect":
            return
        data = message.get("bytes")
        if data is None:  # text frames are not expected
            await _force_close(conn, CLOSE_BAD_MESSAGE)
            return
        if len(data) > ws.max_frame_bytes:
            await _force_close(conn, CLOSE_BAD_MESSAGE)
            return
        if not limiter.allow():
            await _force_close(conn, CLOSE_RATE_LIMITED)
            return
        if not await _dispatch(read_message(data), conn, components, ws):
            return
