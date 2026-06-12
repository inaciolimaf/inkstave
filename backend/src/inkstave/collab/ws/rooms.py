"""In-memory connection + room model for the collab WebSocket (spec 29).

Each connection has a dedicated writer task draining a **bounded** send queue to
its socket; producers (Redis forwarder, handshake) only enqueue, so a slow socket
never blocks the room. A producer that finds a connection's queue full reports it
as *overflowed* — the transport closes such a connection with code 4408.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

# --- WebSocket close codes (spec 29 §5.2.5) ------------------------------- #
CLOSE_NORMAL = 1000
CLOSE_DEAD = 4000  # ping timeout / connection dead
CLOSE_BAD_MESSAGE = 4400  # bad/oversize message
CLOSE_UNAUTHORIZED = 4401  # JWT missing/invalid/expired
CLOSE_FORBIDDEN = 4403  # not a collaborator
CLOSE_NOT_FOUND = 4404  # unknown project/document
CLOSE_SLOW_CONSUMER = 4408  # send buffer overflow
CLOSE_RATE_LIMITED = 4429  # too many messages


@dataclass
class Connection:
    id: str  # uuid4 hex; used as the update origin
    user_id: UUID
    document_id: UUID
    websocket: object  # starlette WebSocket (avoids a hard import here)
    send_queue: asyncio.Queue[bytes]
    awareness_client_id: int | None = None
    closed: bool = False
    # Viewer connections join read-only: their Yjs updates are dropped (spec 34).
    can_write: bool = True
    # Set by the WS endpoint; lets history capture (spec 36) tag rows with the project.
    project_id: UUID | None = None

    def try_enqueue(self, payload: bytes) -> bool:
        """Non-blocking enqueue; ``False`` if the send queue is full (slow socket)."""
        try:
            self.send_queue.put_nowait(payload)
            return True
        except asyncio.QueueFull:
            return False

    async def enqueue_timed(self, payload: bytes, timeout_ms: int) -> bool:
        """Enqueue with a short grace window (spec 29 §5.2.4 / spec 68 #108).

        Gives a momentarily-full queue ``timeout_ms`` to drain before declaring the
        socket a slow consumer. Returns ``True`` on success, ``False`` on timeout —
        the caller then closes the connection with :data:`CLOSE_SLOW_CONSUMER` (4408).
        A non-positive timeout degrades to a non-blocking ``put_nowait``.
        """
        if timeout_ms <= 0:
            return self.try_enqueue(payload)
        try:
            await asyncio.wait_for(self.send_queue.put(payload), timeout=timeout_ms / 1000)
            return True
        except (TimeoutError, asyncio.TimeoutError):
            return False


@dataclass
class Room:
    document_id: UUID
    connections: dict[str, Connection] = field(default_factory=dict)


class RoomManager:
    """Local (per-instance) room membership. Cross-instance fan-out is via Redis."""

    def __init__(self, slow_client_timeout_ms: int = 0) -> None:
        self._rooms: dict[UUID, Room] = {}
        # Grace window for a momentarily-full send queue before a socket is ejected
        # as a slow consumer (spec 68 #108). 0 keeps the legacy non-blocking behaviour.
        self._slow_client_timeout_ms = slow_client_timeout_ms

    def join(self, conn: Connection) -> tuple[Room, bool]:
        """Add ``conn`` to its document's room. Returns ``(room, created_new)`` where
        ``created_new`` is True when this is the first local member (caller then
        subscribes to Redis)."""
        room = self._rooms.get(conn.document_id)
        created = room is None
        if room is None:
            room = Room(conn.document_id)
            self._rooms[conn.document_id] = room
        room.connections[conn.id] = conn
        return room, created

    def leave(self, conn: Connection) -> bool:
        """Remove ``conn``; returns True if its room became empty (caller tears down
        the Redis subscription)."""
        room = self._rooms.get(conn.document_id)
        if room is None:
            return False
        room.connections.pop(conn.id, None)
        if not room.connections:
            self._rooms.pop(conn.document_id, None)
            return True
        return False

    def local_broadcast(
        self, document_id: UUID, payload: bytes, exclude: str | None
    ) -> list[Connection]:
        """Enqueue ``payload`` to every local connection except ``exclude``.
        Returns the connections whose queue was full (to be closed as slow)."""
        room = self._rooms.get(document_id)
        if room is None:
            return []
        overflowed: list[Connection] = []
        for conn_id, conn in list(room.connections.items()):
            if conn_id == exclude or conn.closed:
                continue
            if not conn.try_enqueue(payload):
                overflowed.append(conn)
        return overflowed

    async def local_broadcast_timed(
        self, document_id: UUID, payload: bytes, exclude: str | None
    ) -> list[Connection]:
        """Like :meth:`local_broadcast` but gives each slow socket the configured
        ``COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS`` grace window before declaring it
        overflowed (spec 68 #108). Returns the connections that timed out — the
        transport closes them with :data:`CLOSE_SLOW_CONSUMER` (4408)."""
        room = self._rooms.get(document_id)
        if room is None:
            return []
        overflowed: list[Connection] = []
        for conn_id, conn in list(room.connections.items()):
            if conn_id == exclude or conn.closed:
                continue
            if not await conn.enqueue_timed(payload, self._slow_client_timeout_ms):
                overflowed.append(conn)
        return overflowed

    def is_empty(self, document_id: UUID) -> bool:
        return document_id not in self._rooms

    def room_count(self) -> int:
        return len(self._rooms)
