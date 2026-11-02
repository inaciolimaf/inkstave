"""Builds the real LLM client that ``AGENT_LLM_PROVIDER`` names."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inkstave.core.config.agent import AgentSettings
    from inkstave.modules.agent.llm.base import LLMClient


def build_llm_client(settings: AgentSettings) -> LLMClient:
    """The configured client, imported lazily. Requires that provider's API key."""
    if settings.agent_llm_provider == "openrouter":
        from inkstave.modules.agent.llm.openrouter import OpenRouterLLMClient

        return OpenRouterLLMClient(settings)
    from inkstave.modules.agent.llm.anthropic_client import AnthropicLLMClient

    return AnthropicLLMClient(settings)
