"""FrozenClock test helper (spec 94 §5.5).

Satisfies the :class:`inkstave.time.Clock` protocol, returns a fixed tz-aware UTC
time, and can be advanced so tests can step across an ``exp``/cutoff boundary
without any real sleep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# A fixed, arbitrary tz-aware instant well clear of DST edge cases.
_DEFAULT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FrozenClock:
    def __init__(self, at: datetime | None = None) -> None:
        self._now = at if at is not None else _DEFAULT

    def now(self) -> datetime:
        return self._now

    def advance(self, *, seconds: float = 0) -> None:
        self._now += timedelta(seconds=seconds)

    def set(self, at: datetime) -> None:
        self._now = at
