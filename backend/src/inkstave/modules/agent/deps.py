"""FastAPI dependencies for the agent (spec 41).

These construct the *real* LLM client from settings and are used by spec 44.
Tests never call them — they build ``AgentDeps`` directly with ``FakeLLM`` (or use
``app.dependency_overrides``).
"""

from __future__ import annotations

from fastapi import Depends, Request

from inkstave.core.config.agent import get_agent_settings
from inkstave.core.config.settings import Settings
from inkstave.core.deps import get_settings_dep
from inkstave.modules.agent.graph.agent_deps import AgentDeps
from inkstave.modules.agent.llm.base import LLMClient
from inkstave.modules.agent.llm.factory import build_llm_client
from inkstave.modules.agent.runs.enqueuer import AgentEnqueuer
from inkstave.modules.agent.tools import default_registry


def get_llm_client() -> LLMClient:
    """Construct the configured LLM client. Requires the provider's key at call time."""
    return build_llm_client(get_agent_settings())


def get_agent_deps() -> AgentDeps:
    settings = get_agent_settings()
    return AgentDeps(llm=build_llm_client(settings), settings=settings, tools=default_registry())


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
