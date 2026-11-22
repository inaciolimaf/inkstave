"""Application-level keepalive for the collab WebSocket (spec 29).

Uvicorn owns the protocol-level ping, and the ASGI interface cannot reach it. So the
server pings the browser itself every ``COLLAB_WS_PING_INTERVAL_SECONDS``, and a peer
that has sent nothing for interval + ``COLLAB_WS_PONG_TIMEOUT_SECONDS`` is closed with
``CLOSE_DEAD`` (4000). Any inbound frame counts as proof of life, not only a pong.
"""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import TYPE_CHECKING

from inkstave.modules.collab.crdt.protocol import encode_heartbeat_ping
from inkstave.modules.collab.ws.connection import _force_close
from inkstave.modules.collab.ws.rooms import CLOSE_DEAD, Connection

if TYPE_CHECKING:
    from inkstave.modules.collab.ws.components import CollabWsSettings


async def _heartbeat(conn: Connection, ws: CollabWsSettings) -> None:
    """Ping the peer each interval; close it once it has been silent too long."""
    interval = ws.ping_interval_seconds
    if interval <= 0:  # keepalive disabled
        return
    silence_limit = interval + ws.pong_timeout_seconds
    # Silence counts from here, not from the socket's accept: joining the room may take a while.
    conn.last_seen = monotonic()
    while not conn.closed:
        await asyncio.sleep(interval)
        if monotonic() - conn.last_seen > silence_limit:
            await _force_close(conn, CLOSE_DEAD)
            return
        conn.try_enqueue(encode_heartbeat_ping())
