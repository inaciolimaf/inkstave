"""The session dependency commits before the response leaves, whatever the dependency chain."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse

from inkstave.core.db.session import UNIT_OF_WORK, get_session_factory
from inkstave.core.errors import ConflictError
from inkstave.core.exception_handlers import register_exception_handlers


class FakeSession:
    def __init__(self, log: list[str], *, commit_fails: bool) -> None:
        self._log = log
        self._commit_fails = commit_fails

    async def commit(self) -> None:
        self._log.append("commit")
        if self._commit_fails:
            raise RuntimeError("connection lost at commit")

    async def rollback(self) -> None:
        self._log.append("rollback")

    async def close(self) -> None:
        self._log.append("close")


class Harness:
    def __init__(self, *, commit_fails: bool = False) -> None:
        self.log: list[str] = []
        self.sessions: list[FakeSession] = []
        self.commit_fails = commit_fails
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.app.dependency_overrides[get_session_factory] = lambda: self.factory

    def factory(self) -> FakeSession:
        self.sessions.append(FakeSession(self.log, commit_fails=self.commit_fails))
        return self.sessions[-1]

    async def get(self, path: str) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)


def _add_chained_route(harness: Harness) -> None:
    async def inner(session: Any = UNIT_OF_WORK) -> Any:
        return session

    async def outer(session: Any = UNIT_OF_WORK, from_inner: Any = Depends(inner)) -> Any:
        return session, from_inner

    @harness.app.get("/chain")
    async def route(session: Any = UNIT_OF_WORK, pair: Any = Depends(outer)) -> dict[str, bool]:
        harness.log.append("route")
        return {"shared": all(other is session for other in pair)}


async def test_chained_dependencies_share_one_session_committed_after_the_route() -> None:
    harness = Harness()
    _add_chained_route(harness)

    response = await harness.get("/chain")

    assert response.json() == {"shared": True}
    assert len(harness.sessions) == 1
    assert harness.log == ["route", "commit", "close"]


async def test_a_failed_commit_is_a_500_not_a_200() -> None:
    harness = Harness(commit_fails=True)
    _add_chained_route(harness)

    response = await harness.get("/chain")

    assert response.status_code == 500
    assert response.json()["error"]["type"] == "internal_error"
    assert harness.log == ["route", "commit", "rollback", "close"]


async def test_a_domain_error_rolls_back_and_keeps_its_status() -> None:
    harness = Harness()

    @harness.app.get("/conflict")
    async def route(session: Any = UNIT_OF_WORK) -> None:
        raise ConflictError("Already there.")

    response = await harness.get("/conflict")

    assert response.status_code == 409
    assert harness.log == ["rollback", "close"]


async def test_the_session_is_closed_before_a_streaming_body_starts() -> None:
    harness = Harness()

    async def body() -> AsyncIterator[bytes]:
        harness.log.append("first chunk")
        yield b"x"

    @harness.app.get("/stream")
    async def route(session: Any = UNIT_OF_WORK) -> StreamingResponse:
        return StreamingResponse(body())

    await harness.get("/stream")

    assert harness.log == ["commit", "close", "first chunk"]


async def test_each_request_gets_its_own_session() -> None:
    harness = Harness()
    _add_chained_route(harness)

    await harness.get("/chain")
    await harness.get("/chain")

    assert len(harness.sessions) == 2
