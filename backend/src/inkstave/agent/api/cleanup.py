"""The optional ``agent_audit_cleanup`` ARQ cron (spec 49 §5.1/§5.4; spec 68 #207).

Pure structural split of :mod:`inkstave.agent.api.jobs`; re-exported from there so
the worker registration path is unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete

from inkstave.agent.safety.models import AgentAuditLog


async def agent_audit_cleanup(ctx: dict[str, Any]) -> dict[str, int]:
    """Optional ARQ cron: prune agent-audit rows older than the retention window
    (spec 49 §5.1/§5.4; spec 68 #207).

    Off by default: when ``agent_audit_retention_days`` is non-positive (0 = keep
    forever), this is a no-op and deletes nothing. When positive, it deletes rows
    whose ``created_at`` is older than the window, mirroring ``cleanup_compile_outputs``.
    """
    settings = ctx.get("agent_settings") or ctx["settings"]
    retention_days = getattr(settings, "agent_audit_retention_days", 0)
    if not retention_days or retention_days <= 0:
        return {"pruned": 0}
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    async with ctx["session_factory"]() as session:
        result = await session.execute(
            delete(AgentAuditLog).where(AgentAuditLog.created_at < cutoff)
        )
        await session.commit()
        return {"pruned": int(result.rowcount or 0)}
