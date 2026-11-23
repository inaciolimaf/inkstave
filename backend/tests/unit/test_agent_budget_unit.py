"""Unit tests for the agent's token and cost budgets (spec 49): pure functions and fake Redis, no database.

The Redis keys are read back literally: they are the schema of the per-day counters.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.safety.budget import (
    BudgetDecision,
    cost_for,
    is_budget_exempt,
    model_rates,
    precheck_day,
    record_usage,
    run_cost_exceeded,
    run_tokens_exceeded,
    without_budget_caps,
)

HAIKU = "claude-haiku-5-5"  # first entry of the default cost table
GPT_MINI = "openai/gpt-4o-mini"  # second entry
DAY_SECONDS = 86_400
TTL_TWO_DAYS = 172_800
CAP_NAMES = (
    "agent_max_tokens_per_run",
    "agent_max_cost_per_run_usd",
    "agent_max_tokens_per_day_per_project",
    "agent_max_cost_per_day_per_user_usd",
    "agent_max_total_tokens",
)


def _proj_key(project_id: Any, day: int) -> str:
    return f"agent:day:proj:{project_id}:{day}:tokens"


def _user_key(user_id: Any, day: int) -> str:
    return f"agent:day:user:{user_id}:{day}:microusd"


# --- per-run caps -------------------------------------------------------------------------


@pytest.mark.parametrize(("total", "expected"), [(99, False), (100, True), (101, True)])
def test_run_token_cap_trips_exactly_at_the_cap(total: int, expected: bool) -> None:
    assert run_tokens_exceeded(total, AgentSettings(agent_max_tokens_per_run=100)) is expected


def test_a_run_token_cap_of_one_trips_on_the_first_token() -> None:
    assert run_tokens_exceeded(1, AgentSettings(agent_max_tokens_per_run=1)) is True
    assert run_tokens_exceeded(0, AgentSettings(agent_max_tokens_per_run=1)) is False


def test_a_zero_run_token_cap_is_disabled() -> None:
    assert run_tokens_exceeded(0, AgentSettings(agent_max_tokens_per_run=0)) is False
    assert run_tokens_exceeded(10**9, AgentSettings(agent_max_tokens_per_run=0)) is False


@pytest.mark.parametrize(("cost", "expected"), [(0.29, False), (0.30, True), (0.31, True)])
def test_run_cost_cap_trips_exactly_at_the_cap(cost: float, expected: bool) -> None:
    assert run_cost_exceeded(cost, AgentSettings(agent_max_cost_per_run_usd=0.30)) is expected


def test_a_run_cost_cap_of_one_dollar_trips_at_one_dollar() -> None:
    assert run_cost_exceeded(1.0, AgentSettings(agent_max_cost_per_run_usd=1.0)) is True
    assert run_cost_exceeded(0.99, AgentSettings(agent_max_cost_per_run_usd=1.0)) is False


def test_a_zero_run_cost_cap_is_disabled_even_at_zero_spend() -> None:
    assert run_cost_exceeded(0.0, AgentSettings(agent_max_cost_per_run_usd=0.0)) is False
    assert run_cost_exceeded(5.0, AgentSettings(agent_max_cost_per_run_usd=0.0)) is False


# --- rates and cost -----------------------------------------------------------------------


def test_cost_for_applies_each_rate_to_its_own_side() -> None:
    settings = AgentSettings(agent_model_cost_table={HAIKU: {"input": 0.0001, "output": 0.0005}})
    # 2 000 prompt tokens at 0.0001 per 1K plus 1 000 completion tokens at 0.0005 per 1K.
    assert cost_for(settings, HAIKU, prompt=2000, completion=1000) == Decimal("0.0007")


def test_cost_for_uses_the_rates_of_the_named_model() -> None:
    settings = AgentSettings(
        agent_model_cost_table={
            HAIKU: {"input": 0.0001, "output": 0.0005},
            GPT_MINI: {"input": 0.00015, "output": 0.0006},
        }
    )
    assert cost_for(settings, GPT_MINI, prompt=1000, completion=1000) == Decimal("0.00075")


def test_model_rates_returns_the_named_entry() -> None:
    settings = AgentSettings()
    assert model_rates(settings, GPT_MINI) == {"input": 0.00015, "output": 0.0006}


def test_an_unknown_model_is_priced_at_the_first_table_entry() -> None:
    settings = AgentSettings()
    assert model_rates(settings, "not/a-model") == {"input": 0.0001, "output": 0.0005}


def test_an_empty_cost_table_falls_back_to_the_default_rate() -> None:
    settings = AgentSettings(agent_model_cost_table={})
    assert model_rates(settings, HAIKU) == {"input": 0.00015, "output": 0.0006}
    assert cost_for(settings, HAIKU, prompt=1000, completion=1000) == Decimal("0.00075")


# --- budget exemption ---------------------------------------------------------------------

EXEMPT_LIST = "Ana@Example.com, bob@example.com ,,"


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("ana@example.com", True),  # listed in capitals: matched in lower case
        ("ANA@EXAMPLE.COM", True),  # the e-mail is folded to lower case too
        ("  bob@example.com  ", True),  # surrounding spaces are ignored
        ("carol@example.com", False),
        ("ana@example.co", False),
    ],
)
def test_budget_exemption_ignores_case_and_spaces(email: str, expected: bool) -> None:
    settings = AgentSettings(agent_budget_exempt_emails=EXEMPT_LIST)
    assert is_budget_exempt(settings, email) is expected


def test_the_exemption_list_is_split_on_commas_only() -> None:
    # A space between two addresses must not join them: the second one is still matched alone.
    settings = AgentSettings(agent_budget_exempt_emails="one@example.com, two@example.com")
    assert is_budget_exempt(settings, "one@example.com") is True
    assert is_budget_exempt(settings, "two@example.com") is True


def test_an_empty_exemption_list_exempts_nobody() -> None:
    assert is_budget_exempt(AgentSettings(), "ana@example.com") is False
    assert is_budget_exempt(AgentSettings(agent_budget_exempt_emails=",  ,"), "") is False


def test_an_empty_address_is_never_exempt_from_a_non_empty_list() -> None:
    settings = AgentSettings(agent_budget_exempt_emails="ana@example.com")
    assert is_budget_exempt(settings, "") is False


def test_a_settings_object_without_the_field_exempts_nobody() -> None:
    # A test context may carry something other than AgentSettings; the default is an empty list.
    bare = cast(AgentSettings, SimpleNamespace())
    assert is_budget_exempt(bare, "xxxx") is False
    assert is_budget_exempt(bare, "ana@example.com") is False
    carrying = cast(AgentSettings, SimpleNamespace(agent_budget_exempt_emails="ana@example.com"))
    assert is_budget_exempt(carrying, "ana@example.com") is True


# --- without_budget_caps ------------------------------------------------------------------


def test_without_budget_caps_zeroes_every_token_and_cost_cap() -> None:
    base = AgentSettings(agent_max_runs_per_minute_per_user=7)
    off = without_budget_caps(base)
    for name in CAP_NAMES:
        assert getattr(off, name) == 0, name
    assert off.agent_max_runs_per_minute_per_user == 7  # rate limits still apply to exempt users


def test_without_budget_caps_leaves_the_original_settings_untouched() -> None:
    base = AgentSettings()
    without_budget_caps(base)
    assert base.agent_max_tokens_per_run == 1_000_000
    assert base.agent_max_cost_per_run_usd == 0.30


# --- per-day counters: precheck and record ------------------------------------------------


async def test_the_project_day_cap_trips_exactly_at_the_cap(redis: Any) -> None:
    settings = AgentSettings(agent_max_tokens_per_day_per_project=100)
    project, user = uuid4(), uuid4()
    for used, allowed in ((99, True), (100, False), (101, False)):
        await redis.set(_proj_key(project, 0), used)
        decision = await precheck_day(redis, settings, user_id=user, project_id=project, now=0.0)
        assert decision.allowed is allowed, used
        if not allowed:
            assert decision.reason == "project_day_tokens"


async def test_a_zero_project_day_cap_is_disabled(redis: Any) -> None:
    settings = AgentSettings(agent_max_tokens_per_day_per_project=0)
    project, user = uuid4(), uuid4()
    await redis.set(_proj_key(project, 0), 5)
    decision = await precheck_day(redis, settings, user_id=user, project_id=project, now=0.0)
    assert decision == BudgetDecision(True)


async def test_a_project_day_cap_of_one_trips_on_the_first_token(redis: Any) -> None:
    settings = AgentSettings(agent_max_tokens_per_day_per_project=1)
    project, user = uuid4(), uuid4()
    await redis.set(_proj_key(project, 0), 1)
    decision = await precheck_day(redis, settings, user_id=user, project_id=project, now=0.0)
    assert decision == BudgetDecision(False, "project_day_tokens")


async def test_the_user_day_cost_cap_trips_exactly_at_the_cap(redis: Any) -> None:
    # 0.30 USD is 300 000 micro-dollars: the cap is inclusive, one micro-dollar below it is allowed.
    settings = AgentSettings(agent_max_cost_per_day_per_user_usd=0.30)
    project, user = uuid4(), uuid4()
    for used, allowed in ((299_999, True), (300_000, False), (300_001, False)):
        await redis.set(_user_key(user, 0), used)
        decision = await precheck_day(redis, settings, user_id=user, project_id=project, now=0.0)
        assert decision.allowed is allowed, used
        if not allowed:
            assert decision.reason == "user_day_cost"


async def test_a_zero_user_day_cost_cap_is_disabled(redis: Any) -> None:
    settings = AgentSettings(agent_max_cost_per_day_per_user_usd=0.0)
    project, user = uuid4(), uuid4()
    await redis.set(_user_key(user, 0), 1)
    decision = await precheck_day(redis, settings, user_id=user, project_id=project, now=0.0)
    assert decision == BudgetDecision(True)


async def test_a_user_day_cost_cap_of_one_dollar_is_read_in_dollars(redis: Any) -> None:
    settings = AgentSettings(agent_max_cost_per_day_per_user_usd=1.0)
    project, user = uuid4(), uuid4()
    await redis.set(_user_key(user, 0), 999_999)
    assert (await precheck_day(redis, settings, user_id=user, project_id=project, now=0.0)).allowed
    await redis.set(_user_key(user, 0), 1_000_000)
    decision = await precheck_day(redis, settings, user_id=user, project_id=project, now=0.0)
    assert decision == BudgetDecision(False, "user_day_cost")


async def test_a_spent_user_is_refused_under_that_users_key_only(redis: Any) -> None:
    settings = AgentSettings(agent_max_cost_per_day_per_user_usd=0.30)
    spent, other, project = uuid4(), uuid4(), uuid4()
    await redis.set(_user_key(spent, 0), 300_000)
    refused = await precheck_day(redis, settings, user_id=spent, project_id=project, now=0.0)
    allowed = await precheck_day(redis, settings, user_id=other, project_id=project, now=0.0)
    assert refused == BudgetDecision(False, "user_day_cost")
    assert allowed == BudgetDecision(True)


async def test_record_usage_adds_tokens_and_micro_dollars_to_their_own_counters(redis: Any) -> None:
    project, user = uuid4(), uuid4()
    await record_usage(redis, user_id=user, project_id=project, now=0.0, tokens=40, cost=Decimal("1.5"))
    await record_usage(redis, user_id=user, project_id=project, now=0.0, tokens=2, cost=Decimal("0"))
    assert int(await redis.get(_proj_key(project, 0))) == 42
    assert int(await redis.get(_user_key(user, 0))) == 1_500_000


async def test_record_usage_writes_the_keys_it_names_and_nothing_else(redis: Any) -> None:
    project, user = uuid4(), uuid4()
    await record_usage(redis, user_id=user, project_id=project, now=0.0, tokens=7, cost=Decimal("0.5"))
    assert sorted(await redis.keys("agent:day:*")) == sorted(
        [_proj_key(project, 0).encode(), _user_key(user, 0).encode()]
    )


async def test_record_usage_counters_expire_after_two_days(redis: Any) -> None:
    project, user = uuid4(), uuid4()
    await record_usage(redis, user_id=user, project_id=project, now=0.0, tokens=1, cost=Decimal("0.1"))
    assert await redis.ttl(_proj_key(project, 0)) == TTL_TWO_DAYS
    assert await redis.ttl(_user_key(user, 0)) == TTL_TWO_DAYS


async def test_the_day_bucket_is_the_whole_utc_day(redis: Any) -> None:
    project, user = uuid4(), uuid4()
    # 86 399.9 s is still day 0; 86 400 s starts day 1. Both bucket keys are named by the integer day.
    await record_usage(redis, user_id=user, project_id=project, now=86_399.9, tokens=1, cost=Decimal("0"))
    await record_usage(
        redis, user_id=user, project_id=project, now=float(DAY_SECONDS), tokens=2, cost=Decimal("0")
    )
    assert int(await redis.get(_proj_key(project, 0))) == 1
    assert int(await redis.get(_proj_key(project, 1))) == 2


async def test_yesterdays_spend_does_not_block_today(redis: Any) -> None:
    settings = AgentSettings(agent_max_tokens_per_day_per_project=100)
    project, user = uuid4(), uuid4()
    await record_usage(redis, user_id=user, project_id=project, now=86_399.9, tokens=100, cost=Decimal("0"))
    still_today = await precheck_day(redis, settings, user_id=user, project_id=project, now=86_399.0)
    tomorrow = await precheck_day(redis, settings, user_id=user, project_id=project, now=float(DAY_SECONDS))
    assert still_today == BudgetDecision(False, "project_day_tokens")
    assert tomorrow == BudgetDecision(True)
