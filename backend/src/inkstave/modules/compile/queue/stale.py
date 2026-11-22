"""What counts as a stuck compile: an active row older than its deadline (spec 22, reaper).

A ``queued`` row whose job never ran (lost before pickup, or the API died before the enqueue)
and a ``running`` row whose worker died or whose ARQ timeout cancelled the job both stay
active forever without a deadline. The deadlines derive from ``COMPILE_JOB_TIMEOUT_S``:

- a running compile gets its job timeout plus a grace period (ARQ kills the job at the timeout,
  so anything still running past that is gone);
- a queued compile gets five job timeouts, because the queue wait is not bounded by the job.

Coalescing and the concurrency caps ignore stale rows, and the reaper settles them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_

from inkstave.modules.compile.models.compile import Compile, CompileJobStatus

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement

    from inkstave.core.config.settings import Settings

RUNNING_GRACE_S = 120
QUEUED_JOB_TIMEOUTS = 5

_ACTIVE = (CompileJobStatus.QUEUED.value, CompileJobStatus.RUNNING.value)


@dataclass(frozen=True, slots=True)
class StaleCutoffs:
    """Rows whose clock started before these instants are stale."""

    queued_before: datetime  # queued rows created before this
    running_before: datetime  # running rows started (or created) before this


def stale_cutoffs(settings: Settings, now: datetime | None = None) -> StaleCutoffs:
    now = now or datetime.now(UTC)
    job_s = settings.compile_job_timeout_s
    return StaleCutoffs(
        queued_before=now - timedelta(seconds=job_s * QUEUED_JOB_TIMEOUTS),
        running_before=now - timedelta(seconds=job_s + RUNNING_GRACE_S),
    )


def stale_clause(cutoffs: StaleCutoffs) -> ColumnElement[bool]:
    """Active rows past their deadline."""
    started = func.coalesce(Compile.started_at, Compile.created_at)
    return or_(
        and_(Compile.status == CompileJobStatus.QUEUED.value, Compile.created_at < cutoffs.queued_before),
        and_(Compile.status == CompileJobStatus.RUNNING.value, started < cutoffs.running_before),
    )


def fresh_active_clause(cutoffs: StaleCutoffs) -> ColumnElement[bool]:
    """Active rows still within their deadline: the only ones coalescing and the caps see."""
    return and_(Compile.status.in_(_ACTIVE), ~stale_clause(cutoffs))
