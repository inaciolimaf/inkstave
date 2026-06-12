"""Test harness for the collab WebSocket (spec 29): an in-process ASGI WS client
and helpers to wire the per-instance collab components onto the app."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.collab.protocol import (
    SyncUpdate,
    encode_awareness,
    encode_update,
    read_message,
)
from inkstave.collab.ws.components import build_collab_components
from inkstave.collab.ydocument import YDocument
from inkstave.config import Settings


class SessionCtx:
    """Yield the shared transactional test session (no commit/close on exit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def session_factory(db_session: AsyncSession) -> Any:
    return lambda: SessionCtx(db_session)


def install_collab(app: Any, db_session: AsyncSession, redis: Any, **overrides: Any) -> Any:
    """Build collab components bound to the test session + redis and set them on
    ``app.state.collab``. Returns the components for direct inspection."""
    settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
    components = build_collab_components(
        redis=redis,
        session_factory=session_factory(db_session),
        settings=settings,
        instance_id="instance-test",
    )
    app.state.collab = components
    return components


def make_update(text: str) -> bytes:
    """A SYNC_UPDATE message inserting ``text`` into a fresh document."""
    doc = YDocument()
    collected: list[bytes] = []
    doc.observe(lambda update, _origin: collected.append(update))
    doc.replace_text(text)
    return encode_update(collected[-1])


def awareness_message(state: dict[str, object]) -> tuple[int, bytes]:
    """An awareness message advertising ``state`` for a fresh client."""
    from pycrdt import Awareness, Doc

    client = Awareness(Doc())
    client.set_local_state(state)
    return client.client_id, encode_awareness(client.encode_awareness_update([client.client_id]))


def apply_update_message(doc: YDocument, message_bytes: bytes) -> None:
    parsed = read_message(message_bytes)
    if isinstance(parsed, SyncUpdate):
        doc.apply_update(parsed.update)


class ASGIWebSocketClient:
    """Drive a Starlette WebSocket endpoint in-process over the raw ASGI protocol,
    on the *same* event loop as the test (so the shared session works)."""

    def __init__(self, app: Any, path: str, query: str = "", outbox_max: int = 0) -> None:
        self._app = app
        self._scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [],
            "client": ("testclient", 1),
            "server": ("testserver", 80),
            "subprotocols": [],
        }
        self._inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=outbox_max)
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> ASGIWebSocketClient:
        await self._inbox.put({"type": "websocket.connect"})
        self._task = asyncio.create_task(self._run())
        return self

    async def _run(self) -> None:
        try:
            await self._app(self._scope, self._inbox.get, self._outbox.put)
        except Exception:  # surfaced via a sentinel so receive() doesn't hang
            await self._outbox.put({"type": "websocket.close", "code": 1011})

    async def receive(self, timeout: float = 2.0) -> dict[str, Any]:
        async with asyncio.timeout(timeout):
            return await self._outbox.get()

    async def expect_accept(self, timeout: float = 2.0) -> None:
        message = await self.receive(timeout)
        assert message["type"] == "websocket.accept", message

    async def receive_bytes(self, timeout: float = 2.0) -> bytes:
        message = await self.receive(timeout)
        assert message["type"] == "websocket.send", message
        return message["bytes"]

    async def close_code(self, timeout: float = 2.0) -> int:
        message = await self.receive(timeout)
        assert message["type"] == "websocket.close", message
        return int(message["code"])

    async def expect_no_message(self, timeout: float = 0.2) -> None:
        try:
            message = await self.receive(timeout)
        except TimeoutError:
            return
        raise AssertionError(f"unexpected message: {message}")

    async def send_bytes(self, data: bytes) -> None:
        await self._inbox.put({"type": "websocket.receive", "bytes": data})

    async def send_text(self, text: str) -> None:
        await self._inbox.put({"type": "websocket.receive", "text": text})

    async def disconnect(self) -> None:
        await self._inbox.put({"type": "websocket.disconnect", "code": 1006})

    async def __aexit__(self, *_exc: object) -> None:
        await self.disconnect()
        if self._task is not None:
            try:
                async with asyncio.timeout(2.0):
                    await self._task
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()


__all__ = [
    "ASGIWebSocketClient",
    "SessionCtx",
    "apply_update_message",
    "awareness_message",
    "install_collab",
    "make_update",
    "session_factory",
]
