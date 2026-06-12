"""Unit tests for the optional agent_audit_cleanup ARQ task (spec 49 §5.1/§5.4;
spec 68 #207).

The task is gated by ``agent_audit_retention_days``: when non-positive it is a
no-op and never opens a session. It is also registered on the worker so the cron
entry can drive it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from inkstave.agent.api.jobs import agent_audit_cleanup


async def test_cleanup_is_noop_when_retention_unset() -> None:
    # retention=0 means "keep forever": the job must delete nothing and must never
    # call session_factory (so a missing/raising factory is fine).
    def _factory() -> Any:  # pragma: no cover - must not be called
        raise AssertionError("no DB session expected when retention is unset")

    ctx: dict[str, Any] = {
        "agent_settings": SimpleNamespace(agent_audit_retention_days=0),
        "session_factory": _factory,
    }
    assert await agent_audit_cleanup(ctx) == {"pruned": 0}


async def test_cleanup_is_noop_when_retention_negative() -> None:
    ctx: dict[str, Any] = {
        "agent_settings": SimpleNamespace(agent_audit_retention_days=-5),
        "session_factory": lambda: None,
    }
    assert await agent_audit_cleanup(ctx) == {"pruned": 0}


def test_cleanup_is_registered_on_the_worker() -> None:
    from inkstave.compile.worker import WorkerSettings

    names = {getattr(f, "name", None) for f in WorkerSettings.functions}
    assert "agent_audit_cleanup" in names
