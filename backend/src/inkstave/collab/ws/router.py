"""Collaboration WebSocket endpoint + connection lifecycle (spec 29).

JWT-authenticated, per-document rooms; relays binary Yjs sync/update/awareness
messages between clients (including across app instances via Redis), driving the
spec-28 ``DocumentManager`` as the single source of truth for state/persistence.

The access token is taken from the ``?token=`` query param (browsers cannot set
Authorization headers on ``WebSocket``). All delivery — local and cross-instance —
goes through Redis so the originating socket is excluded uniformly.

The authorization/connection helpers live in ``connection`` and the inbound
message handling in ``messaging``; both are re-exported here so the public import
surface (``inkstave.collab.ws.router``) is unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, WebSocket

from inkstave.auth.dependencies import authenticate_ws_token
from inkstave.auth.tokens import build_token_service
from inkstave.collab.protocol import encode_awareness, encode_sync_step1
from inkstave.collab.ws.connection import (
    _authorize,
    _cleanup,
    _force_close,
    _make_forwarder,
    _writer,
)
from inkstave.collab.ws.messaging import _dispatch, _receive_loop
from inkstave.collab.ws.rooms import (
    CLOSE_DEAD,
    CLOSE_UNAUTHORIZED,
    Connection,
)
from inkstave.config import get_settings
from inkstave.observability.context import bind_context, clear_context
from inkstave.observability.metrics import track_ws

if TYPE_CHECKING:
    from inkstave.collab.ws.components import CollabComponents

__all__ = [
    "_authorize",
    "_cleanup",
    "_dispatch",
    "_force_close",
    "_make_forwarder",
    "_receive_loop",
    "_writer",
    "router",
]

router = APIRouter()


@router.websocket("/ws/collab/projects/{project_id}/documents/{document_id}")
async def collab_ws(
    websocket: WebSocket,
    project_id: UUID,
    document_id: UUID,
    token: str | None = Query(None),
) -> None:
    components: CollabComponents | None = getattr(websocket.app.state, "collab", None)
    if components is None:
        await websocket.close(code=CLOSE_DEAD)
        return

    settings = get_settings()
    token_service = build_token_service(settings)

    # --- Authenticate + authorize BEFORE accept (never expose room data first). ---
    if not token:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    async with components.session_factory() as session:
        try:
            user = await authenticate_ws_token(token, token_service, session)
        except Exception:
            await websocket.close(code=CLOSE_UNAUTHORIZED)
            return
        deny_code, can_write = await _authorize(session, user, project_id, document_id)
    if deny_code is not None:
        await websocket.close(code=deny_code)
        return

    await websocket.accept()
    # Observability (spec 51): bind WS context + track the active-connections gauge for
    # the whole connection; track_ws/clear_context in finally so a crash never leaks them.
    ctx_tokens = bind_context(
        ws_session_id=uuid4().hex, user_id=str(user.id), project_id=str(project_id)
    )
    try:
        with track_ws("collab"):
            ws = components.ws_settings
            conn = Connection(
                id=uuid4().hex,
                user_id=user.id,
                document_id=document_id,
                websocket=websocket,
                send_queue=asyncio.Queue(maxsize=ws.send_queue_max),
                can_write=can_write,
                project_id=project_id,
            )

            handle = await components.manager.acquire(document_id)
            _room, created = components.rooms.join(conn)
            if created:
                components.subscriptions[document_id] = await components.redis_bridge.subscribe(
                    document_id, _make_forwarder(components, document_id)
                )

            writer = asyncio.create_task(_writer(conn))
            try:
                # Server side of the sync handshake: our Step 1 + the awareness snapshot.
                conn.try_enqueue(encode_sync_step1(handle.ydoc.get_state_vector()))
                # Mark our step1 as sent so a client SyncStep1 doesn't re-send it.
                conn.server_step1_sent = True  # type: ignore[attr-defined]
                snapshot = components.awareness.snapshot(document_id)
                if snapshot is not None:
                    conn.try_enqueue(encode_awareness(snapshot))
                await _receive_loop(conn, components, ws)
            except Exception:
                pass  # abrupt disconnect / socket error — fall through to cleanup
            finally:
                conn.closed = True
                writer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await writer
                await _cleanup(components, conn)
    finally:
        clear_context(ctx_tokens)
