"""Connection-lifecycle helpers for the collab WebSocket (spec 29).

Authorization, the per-connection writer task, forced socket close, the Redis
forwarder, and room cleanup. Kept separate from message dispatch so the public
``router`` module stays a thin transport surface.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.authorization.capabilities import Capability, capabilities_for
from inkstave.authorization.service import role_for
from inkstave.collab.protocol import encode_awareness
from inkstave.collab.ws.redis_bridge import OnMessage
from inkstave.collab.ws.rooms import (
    CLOSE_FORBIDDEN,
    CLOSE_NOT_FOUND,
    CLOSE_SLOW_CONSUMER,
    Connection,
)
from inkstave.db.models.project import Project
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.tree_service import EntityNotFoundError, get_entity

if TYPE_CHECKING:
    from inkstave.collab.ws.components import CollabComponents
    from inkstave.db.models.user import User


async def _authorize(
    session: object, user: User, project_id: UUID, document_id: UUID
) -> tuple[int | None, bool]:
    """Authorize a room join via the central role→capability matrix (spec 34).

    Returns ``(close_code, can_write)``: a non-None close code denies the join
    (4404 unknown project/document, 4403 non-member); ``can_write`` is True for
    owner/editor and False for a viewer (read-only). 404 vs 403 is deliberate —
    a non-member of an *existing* project is still told 4403 (the project id was
    supplied by an authenticated user), while a missing project/doc is 4404.
    """
    project = await session.get(Project, project_id)  # type: ignore[attr-defined]
    if project is None or project.deleted_at is not None:
        return CLOSE_NOT_FOUND, False
    role = await role_for(session, user.id, project_id)  # type: ignore[arg-type]
    if role is None:
        return CLOSE_FORBIDDEN, False  # authenticated non-member
    # Join check (not a raising path): a missing or non-doc id maps to 4404. The
    # helper raises EntityNotFoundError for both (no wrong_type_error supplied).
    try:
        await get_entity(
            session,  # type: ignore[arg-type]
            project_id,
            document_id,
            expected_type=TreeEntityType.doc,
        )
    except EntityNotFoundError:
        return CLOSE_NOT_FOUND, False
    can_write = Capability.COLLAB_WRITE in capabilities_for(role)
    return None, can_write


async def _writer(conn: Connection) -> None:
    """Drain the bounded send queue to the socket; only the receive loop cleans up."""
    try:
        while True:
            payload = await conn.send_queue.get()
            await conn.websocket.send_bytes(payload)  # type: ignore[attr-defined]
    except asyncio.CancelledError:
        raise
    except Exception:
        return


async def _force_close(conn: Connection, code: int) -> None:
    if conn.closed:
        return
    conn.closed = True
    with contextlib.suppress(Exception):
        await conn.websocket.close(code=code)  # type: ignore[attr-defined]


def _make_forwarder(components: CollabComponents, document_id: UUID) -> OnMessage:
    async def on_message(payload: bytes, exclude: str | None) -> None:
        overflowed = components.rooms.local_broadcast(document_id, payload, exclude)
        for conn in overflowed:
            asyncio.create_task(_force_close(conn, CLOSE_SLOW_CONSUMER))

    return on_message


async def _cleanup(components: CollabComponents, conn: Connection) -> None:
    doc_id = conn.document_id
    if conn.awareness_client_id is not None:
        offline = components.awareness.remove_client(doc_id, conn.awareness_client_id)
        if offline is not None:
            with contextlib.suppress(Exception):
                await components.redis_bridge.publish(doc_id, conn.id, encode_awareness(offline))
    await components.manager.release(doc_id)
    if components.rooms.leave(conn):
        subscription = components.subscriptions.pop(doc_id, None)
        if subscription is not None:
            await subscription.aclose()
        components.awareness.drop(doc_id)
        # Room empty: flush any buffered history so closing a doc loses nothing (spec 36).
        if components.history is not None:
            with contextlib.suppress(Exception):
                await components.history.flush_doc(doc_id=doc_id, reason="idle")
