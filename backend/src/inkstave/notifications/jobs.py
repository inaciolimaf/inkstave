"""The notification expiry-sweep ARQ job (spec 39). Idempotent; scheduled by cron."""

from __future__ import annotations

from typing import Any

from inkstave.notifications.service import NotificationService


async def sweep_notifications(ctx: dict[str, Any]) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        removed = await NotificationService(session).sweep_expired()
        await session.commit()
    return {"status": "swept", "removed": removed}
