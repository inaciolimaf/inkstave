"""Collab-WS auth exception visibility (spec 92, issue #A3).

The auth catch was narrowed from `except Exception` to `NotAuthenticatedError`
and now logs a WARNING (with project/document ids, never the token) before
closing 4401. A non-auth error must propagate instead of being masked. Pure unit
test: fakes for the websocket + components, `authenticate_ws_token` monkeypatched.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from inkstave.auth.dependencies import NotAuthenticatedError
from inkstave.collab.ws import router as ws_router
from inkstave.collab.ws.rooms import CLOSE_UNAUTHORIZED


class FakeWS:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.closed_code: int | None = None
        self.accepted = False

    async def close(self, code: int | None = None) -> None:
        self.closed_code = code

    async def accept(self) -> None:
        self.accepted = True


class _FakeSessionCtx:
    async def __aenter__(self) -> Any:
        return SimpleNamespace()

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class FakeComponents:
    def session_factory(self) -> _FakeSessionCtx:
        return _FakeSessionCtx()


def _ws() -> FakeWS:
    app = SimpleNamespace(state=SimpleNamespace(collab=FakeComponents()))
    return FakeWS(app)


async def test_ws_auth_failure_logs_warning_and_closes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _raise(*_a: object, **_k: object) -> Any:
        raise NotAuthenticatedError()

    monkeypatch.setattr(ws_router, "authenticate_ws_token", _raise)
    ws = _ws()
    pid, did = uuid4(), uuid4()
    token = "bad-token-secret-value"

    with caplog.at_level(logging.WARNING):
        await ws_router.collab_ws(ws, pid, did, token=token)

    assert ws.closed_code == CLOSE_UNAUTHORIZED  # close behaviour unchanged
    warnings = [
        r
        for r in caplog.records
        if r.name == "inkstave.collab.ws.router" and r.levelno == logging.WARNING
    ]
    assert warnings, "an auth-failure WARNING should be logged"
    rec = warnings[0]
    assert getattr(rec, "project_id", None) == str(pid)
    assert getattr(rec, "document_id", None) == str(did)
    assert token not in caplog.text  # token never logged


async def test_ws_non_auth_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise(*_a: object, **_k: object) -> Any:
        raise ValueError("db connection lost")

    monkeypatch.setattr(ws_router, "authenticate_ws_token", _raise)
    ws = _ws()

    with pytest.raises(ValueError):
        await ws_router.collab_ws(ws, uuid4(), uuid4(), token="x")
    # The non-auth error surfaced; it was NOT masked as a 4401 close.
    assert ws.closed_code is None
