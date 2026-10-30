"""Injectable clock seam for time-dependent logic (spec 94).

A one-method :class:`Clock` lets security-critical auth code take "now" from an
injected source, so token-expiry / rotation-cutoff / email-change boundary cases
become deterministically testable without real wall-clock time passing. The
default :data:`SYSTEM_CLOCK` wraps exactly ``datetime.now(UTC)`` — the call the
auth code used before — so production behaviour is byte-for-byte unchanged when
no clock is supplied.

Mirrors the existing injected-clock precedent in
``inkstave/agent/api/jobs.py`` (``ctx.get("clock", time.time)``). Intentionally
tiny: one method, UTC-aware, no scheduling / monotonic / async.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """A source of the current time as a timezone-aware UTC ``datetime``."""

    def now(self) -> datetime: ...


class SystemClock:
    """Default clock: the real system clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)


# Module-level default the auth seams fall back to when no clock is injected.
SYSTEM_CLOCK: Clock = SystemClock()
