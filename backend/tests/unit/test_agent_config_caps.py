"""Unit: the agent's default caps are ordered so that each one can trigger (spec 49, spec 44)."""

from __future__ import annotations

from decimal import Decimal

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.safety.budget import cost_for


def test_the_per_run_token_cap_stops_before_the_soft_cap() -> None:
    # Both caps count the same total. The soft cap only ends the loop when the per-run cap is off.
    settings = AgentSettings()
    assert 0 < settings.agent_max_tokens_per_run < settings.agent_max_total_tokens


def test_a_run_at_the_token_cap_with_an_even_split_reaches_the_cost_cap() -> None:
    settings = AgentSettings()
    half = settings.agent_max_tokens_per_run // 2
    cost = cost_for(settings, settings.agent_model, half, half)
    assert cost >= Decimal(str(settings.agent_max_cost_per_run_usd))


def test_the_per_run_cost_cap_fits_inside_the_daily_user_cap() -> None:
    settings = AgentSettings()
    assert settings.agent_max_cost_per_run_usd <= settings.agent_max_cost_per_day_per_user_usd


def test_the_stall_timeout_covers_a_whole_job_plus_one_request() -> None:
    # A live worker always settles a run within the job timeout, so a silence longer than
    # that (plus one request of slack) means the worker died.
    settings = AgentSettings()
    assert settings.stall_timeout_s() == settings.agent_job_timeout_s + settings.agent_request_timeout_s
