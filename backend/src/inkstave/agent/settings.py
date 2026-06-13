"""Agent configuration (spec 41).

Constructing ``AgentSettings`` never requires the API key (so tests/CI load
cleanly); the key is only required when the real ``OpenRouterLLMClient`` is built.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="", extra="ignore", case_sensitive=False
    )

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    agent_model: str = "openai/gpt-4o-mini"
    agent_temperature: float = 0.2
    agent_max_iterations: int = 8
    agent_max_total_tokens: int = 60000
    # Output cap per LLM call. Must be large enough for a propose_edit whose
    # new_text is a whole document — too small truncates the tool-call JSON, which
    # then fails to parse (the "_raw" fallback) and the edit is rejected.
    agent_max_tokens_per_call: int = 32000
    agent_request_timeout_s: int = 120
    # Whole-turn ceiling enforced by ARQ (api/jobs.py runs inside this). Must comfortably
    # exceed a worst-case multi-iteration turn; on overrun the worker cancels the job and
    # the turn is settled as a `timeout` error (never a wedged "running" session).
    agent_job_timeout_s: int = 600
    agent_http_referer: str = "https://inkstave.local"
    agent_app_title: str = "Inkstave"

    # Tool output limits (spec 42).
    agent_tool_read_max_chars: int = 40000
    agent_tool_search_max_results: int = 50
    agent_tool_tree_max_nodes: int = 500
    agent_tool_edit_max_chars: int = 200000

    # Diff generation (spec 43).
    agent_diff_context_lines: int = 3
    agent_diff_max_doc_chars: int = 400000

    # API + streaming (spec 44).
    agent_stream_transport: str = "sse"
    agent_stream_heartbeat_s: int = 15
    agent_run_ttl_s: int = 900
    agent_max_message_chars: int = 8000

    # Context + LaTeX parsing (spec 48).
    agent_context_token_budget: int = 8000
    agent_context_surrounding_lines: int = 40
    agent_section_extra_commands: str = ""
    agent_context_cache: str = "memory"  # memory | redis | off

    # Safety: rate limits, budgets, audit (spec 49). A 0 disables that specific cap.
    agent_max_runs_per_minute_per_user: int = 10
    agent_max_concurrent_runs_per_user: int = 2
    agent_max_runs_per_minute_per_project: int = 20
    agent_max_tokens_per_run: int = 120000
    agent_max_cost_per_run_usd: float = 0.50
    agent_max_tokens_per_day_per_project: int = 2000000
    agent_max_cost_per_day_per_user_usd: float = 10.00
    agent_model_cost_table: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        }
    )
    agent_audit_retention_days: int = 90
    agent_injection_guard: str = "on"  # on | off


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
