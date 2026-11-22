"""Reaper: settle compiles whose job was lost, so they stop holding a slot (spec 22).

A queued or running row with no live job stays active forever, and coalescing would return
it on every request. The reaper runs as an ARQ cron job and marks each stale row ``timeout``
with a message, then publishes the status so an open SSE stream closes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from inkstave.modules.compile.queue.jobs import status_payload
from inkstave.modules.compile.queue.repository import CompileRepository
from inkstave.modules.compile.queue.stale import stale_cutoffs
from inkstave.modules.compile.queue.stream import publish_status

STALE_MESSAGE = "compile did not finish in time: no worker completed it (marked stale by the reaper)"


async def reap_stale_compiles(ctx: dict[str, Any]) -> dict[str, int]:
    """ARQ cron job: settle stale active compiles as ``timeout`` and announce each one."""
    now = datetime.now(UTC)
    cutoffs = stale_cutoffs(ctx["settings"], now)
    async with ctx["session_factory"]() as session:
        rows = await CompileRepository(session).reap_stale(cutoffs, now=now, message=STALE_MESSAGE)
        await session.commit()
    for row in rows:
        await publish_status(ctx["redis"], row.id, status_payload(row))
    return {"reaped": len(rows)}
