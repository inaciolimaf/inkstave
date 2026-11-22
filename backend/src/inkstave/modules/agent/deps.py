"""FastAPI dependencies for the agent (spec 41).

These construct the *real* LLM client from settings and are used by spec 44.
Tests never call them — they build ``AgentDeps`` directly with ``FakeLLM`` (or use
``app.dependency_overrides``).
"""

from __future__ import annotations

from fastapi import Depends, Request

from inkstave.core.config.settings import Settings
from inkstave.core.deps import get_settings_dep
from inkstave.modules.agent.runs.enqueuer import AgentEnqueuer


async def get_agent_enqueuer(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> AgentEnqueuer:
    """Dependency providing the ARQ agent-turn enqueuer (faked in tests)."""
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        request.app.state.arq_pool = pool
    return AgentEnqueuer(pool, settings.compile_queue_name)
