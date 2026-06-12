"""Retention sweep: prune old compile outputs from storage + DB (spec 23)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from inkstave.compile.output_repository import OutputRepository


async def cleanup_compile_outputs(ctx: dict[str, Any]) -> dict[str, int]:
    """ARQ cron job: prune outputs beyond the per-project keep-window or older than
    the max age, in bounded batches. Deletes storage objects + ``compile_outputs``
    rows; leaves the ``compiles`` status row for history.
    """
    settings = ctx["settings"]
    async with ctx["session_factory"]() as session:
        repo = OutputRepository(session)
        store = ctx["make_output_store"](session)
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.compile_retention_max_age_s)
        compile_ids = await repo.list_compiles_for_retention(
            keep_per_project=settings.compile_retain_per_project,
            max_age_cutoff=cutoff,
            batch=settings.compile_retention_batch,
        )
        for compile_id in compile_ids:
            await store.delete_for_compile(compile_id)
        await session.commit()
        return {"pruned": len(compile_ids)}
