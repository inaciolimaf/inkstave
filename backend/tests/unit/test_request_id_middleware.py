"""Unit tests for ``RequestIdMiddleware`` driven over a raw ASGI scope (spec 02 §8).

These exercise the middleware directly — no FastAPI app, no httpx client — to assert
it generates a correlation id when none is supplied and echoes a provided one.
"""

from __future__ import annotations

from typing import Any

from inkstave.middleware import RequestIdMiddleware

HEADER = "x-request-id"


async def _downstream(scope: Any, receive: Any, send: Any) -> None:
    """Minimal ASGI app: emit a 200 response start (the middleware injects the header)."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


def _scope(headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
    }


async def _run(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    """Drive the middleware once and return the response headers it sent (decoded)."""
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = RequestIdMiddleware(_downstream, HEADER)
    await middleware(_scope(headers), receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")
    return {k.decode().lower(): v.decode() for k, v in start["headers"]}


async def test_generates_request_id_when_absent() -> None:
    headers = await _run([])
    generated = headers.get(HEADER)
    assert generated
    assert len(generated) >= 16  # uuid4().hex


async def test_reuses_provided_request_id() -> None:
    headers = await _run([(HEADER.encode(), b"provided-id-123")])
    assert headers.get(HEADER) == "provided-id-123"
