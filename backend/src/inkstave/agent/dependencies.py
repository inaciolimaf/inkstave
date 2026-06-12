"""FastAPI dependencies for the agent (spec 41).

These construct the *real* OpenRouter client from settings and are used by spec 44.
Tests never call them — they build ``AgentDeps`` directly with ``FakeLLM`` (or use
``app.dependency_overrides``).
"""

from __future__ import annotations

from inkstave.agent.deps import AgentDeps
from inkstave.agent.llm.base import LLMClient
from inkstave.agent.llm.openrouter import OpenRouterLLMClient
from inkstave.agent.settings import get_agent_settings
from inkstave.agent.tools import default_registry


def get_llm_client() -> LLMClient:
    """Construct the configured LLM client. Requires OPENROUTER_API_KEY at call time."""
    return OpenRouterLLMClient(get_agent_settings())


def get_agent_deps() -> AgentDeps:
    settings = get_agent_settings()
    return AgentDeps(llm=OpenRouterLLMClient(settings), settings=settings, tools=default_registry())
