"""Helpers shared by the ``test_seeded_*`` integration tests (a lived-in project, see tests/factories)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth import User
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.collab.crdt.protocol import SyncStep2, encode_sync_step1, encode_update, read_message
from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.ws.components import CollabComponents
from tests.collab_ws_harness import ASGIWebSocketClient


def auth_headers(user: User) -> dict[str, str]:
    """Bearer headers for ``user``, minted the way the login flow does."""
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def doc_path(project_id: UUID, document_id: UUID) -> str:
    return f"/ws/collab/projects/{project_id}/documents/{document_id}"


def connect(app: Any, project_id: UUID, document_id: UUID, user: User) -> ASGIWebSocketClient:
    """A collab socket for ``document_id``, authenticated as ``user``. Use it as an async context."""
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return ASGIWebSocketClient(app, doc_path(project_id, document_id), query=f"token={token}")


async def sync_editor(ws: ASGIWebSocketClient) -> YDocument:
    """Join like a browser editor: accept, answer the server's step 1, and apply its step 2.

    The returned document holds whatever the server had (the seeded text on a first open).
    """
    await ws.expect_accept()
    read_message(await ws.receive_bytes())  # the server's step 1
    local = YDocument()
    await ws.send_bytes(encode_sync_step1(local.get_state_vector()))
    while True:
        message = read_message(await ws.receive_bytes())
        if isinstance(message, SyncStep2):
            local.apply_update(message.update)
            return local


async def type_edit(ws: ASGIWebSocketClient, local: YDocument, new_text: str) -> None:
    """Replace the editor's text and send the resulting update, as CodeMirror's binding does."""
    update = local.replace_text(new_text)
    await ws.send_bytes(encode_update(update))


async def edit_over_socket(
    app: Any, components: CollabComponents, project_id: UUID, doc_id: UUID, user: User, new_text: str
) -> None:
    """One editing session: join, type ``new_text``, leave, then capture its history version now."""
    async with connect(app, project_id, doc_id, user) as ws:
        local = await sync_editor(ws)
        await type_edit(ws, local, new_text)
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.05)
    assert components.history is not None
    await components.history.flush_doc(doc_id=doc_id, reason="manual")
