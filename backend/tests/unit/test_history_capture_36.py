"""Fake-clock unit tests for the history capture debounce buffer (spec 36 §8;
spec 68 #143).

These drive ``HistoryCaptureService`` directly with **no Postgres**: the timer is
replaced by a controllable fake (so we observe re-arms without real wall-clock
delay) and the flush sink is stubbed. They cover:

  (a) the debounce timer re-arms on every new update;
  (b) reaching ``HISTORY_FLUSH_MAX_BUFFER`` forces a flush with the threshold reason;
  (c) flushing an empty buffer is a no-op (no session/sink work).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest

from inkstave.core.config.settings import Settings
from inkstave.infra.storage.base import ObjectStore
from inkstave.modules.collab import YDocument
from inkstave.modules.history.versions.capture import HistoryCaptureService


def _settings(**over: Any) -> Settings:
    return Settings(_env_file=None, **over)


class _FakeClock:
    """Records ``call_later`` arm/cancel events instead of scheduling real timers."""

    def __init__(self) -> None:
        self.arms = 0
        self.cancels = 0

    def call_later(self, _delay: float, _cb: Any, *_args: Any) -> _FakeClock:
        self.arms += 1
        return self  # a handle whose .cancel() we count below

    def cancel(self) -> None:
        self.cancels += 1


def _make_service(**over: Any) -> HistoryCaptureService:
    # A session factory that must never be entered in these in-memory tests.
    def _factory() -> Any:  # pragma: no cover - only called if a real flush happens
        raise AssertionError("no DB access expected in fake-clock unit tests")

    return HistoryCaptureService(_factory, cast(ObjectStore, object()), _settings(**over))


async def test_timer_rearms_on_each_update(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    svc = _make_service(history_flush_max_buffer=1000)  # high so threshold never trips
    # Replace the real loop timer with the fake clock's call_later.
    monkeypatch.setattr("inkstave.modules.history.versions.capture.asyncio.get_running_loop", lambda: clock)

    pid, did = uuid4(), uuid4()
    at = datetime.now(UTC)
    for i in range(3):
        await svc.capture_update(project_id=pid, doc_id=did, update=bytes([i]), author_id=None, at=at)

    assert clock.arms == 3  # the debounce timer was (re)armed on every update
    assert clock.cancels == 2  # each re-arm first cancels the prior pending timer


async def test_threshold_forces_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    svc = _make_service(history_flush_max_buffer=3)
    monkeypatch.setattr("inkstave.modules.history.versions.capture.asyncio.get_running_loop", lambda: clock)

    flushes: list[str] = []

    async def fake_flush(*, doc_id: Any, reason: str) -> None:
        flushes.append(reason)

    monkeypatch.setattr(svc, "flush_doc", fake_flush)

    pid, did = uuid4(), uuid4()
    at = datetime.now(UTC)
    # Two updates stay buffered (below the threshold of 3); the third trips it.
    for i in range(3):
        await svc.capture_update(project_id=pid, doc_id=did, update=bytes([i]), author_id=None, at=at)

    assert flushes == ["threshold"]  # exactly one forced flush, at the threshold


async def test_empty_flush_is_noop() -> None:
    # No buffered updates -> flush_doc returns without touching the session factory
    # (which would raise) or the store. An "idle" reason also drops per-doc state.
    svc = _make_service()
    did = uuid4()
    await svc.flush_doc(doc_id=did, reason="idle")  # must not raise / touch DB
    await svc.flush_doc(doc_id=did, reason="manual")  # also a no-op


def _real_updates() -> tuple[YDocument, list[bytes]]:
    """A Yjs document and the updates its edits produce, so the service can merge them."""
    ed = YDocument()
    collected: list[bytes] = []
    ed.observe(lambda update, _origin: collected.append(update))
    return ed, collected


class _DownSession:
    """A session factory whose sessions cannot be opened, as when the database is unreachable."""

    async def __aenter__(self) -> Any:
        raise RuntimeError("database unreachable")

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def test_failed_flush_keeps_updates_and_stops_retrying_after_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    monkeypatch.setattr("inkstave.modules.history.versions.capture.asyncio.get_running_loop", lambda: clock)
    svc = HistoryCaptureService(
        _DownSession, cast(ObjectStore, object()), _settings(history_flush_max_buffer=1000)
    )
    pid, did = uuid4(), uuid4()
    at = datetime.now(UTC)
    ed, updates = _real_updates()
    ed.replace_text("a")
    ed.replace_text("ab")
    for update in updates:
        await svc.capture_update(project_id=pid, doc_id=did, update=update, author_id=None, at=at)

    arms_before = clock.arms
    rearmed: list[bool] = []
    for _ in range(5):
        with pytest.raises(RuntimeError):
            await svc.flush_doc(doc_id=did, reason="idle")
        rearmed.append(clock.arms > arms_before)
        arms_before = clock.arms

    assert len(svc._buffers[did].updates) == 2  # held, never dropped
    assert rearmed == [True, True, True, False, False]  # automatic retries are bounded


async def test_flush_all_continues_past_a_failing_document(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr("inkstave.modules.history.versions.capture.asyncio.get_running_loop", lambda: clock)
    svc = HistoryCaptureService(
        _DownSession, cast(ObjectStore, object()), _settings(history_flush_max_buffer=1000)
    )
    at = datetime.now(UTC)
    docs = [uuid4(), uuid4()]
    for did in docs:
        ed, updates = _real_updates()
        ed.replace_text("x")
        await svc.capture_update(project_id=uuid4(), doc_id=did, update=updates[0], author_id=None, at=at)

    await svc.flush_all()  # every document fails; shutdown must try each one and not raise

    assert all(len(svc._buffers[did].updates) == 1 for did in docs)
