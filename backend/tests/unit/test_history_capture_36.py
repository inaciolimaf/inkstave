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
from typing import Any
from uuid import uuid4

import pytest

from inkstave.config import Settings
from inkstave.history.capture import HistoryCaptureService


def _settings(**over: object) -> Settings:
    return Settings(_env_file=None, **over)  # type: ignore[call-arg]


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


def _make_service(**over: object) -> HistoryCaptureService:
    # A session factory that must never be entered in these in-memory tests.
    def _factory() -> Any:  # pragma: no cover - only called if a real flush happens
        raise AssertionError("no DB access expected in fake-clock unit tests")

    return HistoryCaptureService(_factory, object(), _settings(**over))


async def test_timer_rearms_on_each_update(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    svc = _make_service(history_flush_max_buffer=1000)  # high so threshold never trips
    # Replace the real loop timer with the fake clock's call_later.
    monkeypatch.setattr("inkstave.history.capture.asyncio.get_running_loop", lambda: clock)

    pid, did = uuid4(), uuid4()
    at = datetime.now(UTC)
    for i in range(3):
        await svc.capture_update(
            project_id=pid, doc_id=did, update=bytes([i]), author_id=None, at=at
        )

    assert clock.arms == 3  # the debounce timer was (re)armed on every update
    assert clock.cancels == 2  # each re-arm first cancels the prior pending timer


async def test_threshold_forces_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    svc = _make_service(history_flush_max_buffer=3)
    monkeypatch.setattr("inkstave.history.capture.asyncio.get_running_loop", lambda: clock)

    flushes: list[str] = []

    async def fake_flush(*, doc_id: Any, reason: str) -> None:
        flushes.append(reason)

    monkeypatch.setattr(svc, "flush_doc", fake_flush)

    pid, did = uuid4(), uuid4()
    at = datetime.now(UTC)
    # Two updates stay buffered (below the threshold of 3); the third trips it.
    for i in range(3):
        await svc.capture_update(
            project_id=pid, doc_id=did, update=bytes([i]), author_id=None, at=at
        )

    assert flushes == ["threshold"]  # exactly one forced flush, at the threshold


async def test_empty_flush_is_noop() -> None:
    # No buffered updates -> flush_doc returns without touching the session factory
    # (which would raise) or the store. An "idle" reason also drops per-doc state.
    svc = _make_service()
    did = uuid4()
    await svc.flush_doc(doc_id=did, reason="idle")  # must not raise / touch DB
    await svc.flush_doc(doc_id=did, reason="manual")  # also a no-op
