"""Unit tests for the agent's run rate limits and concurrency slots (spec 49): fake Redis, no database.

The Redis keys are read back literally: they are the schema of the counters.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.safety.rate_limit import acquire_run, check_rate_limit, release_run


def _user_window(user_id: Any, window: int) -> str:
    return f"agent:rl:user:{user_id}:{window}"


def _project_window(project_id: Any, window: int) -> str:
    return f"agent:rl:proj:{project_id}:{window}"


def _concurrency(user_id: Any) -> str:
    return f"agent:conc:user:{user_id}"


async def test_acquire_run_counts_the_user_project_and_concurrency_keys(redis: Any) -> None:
    user, project = uuid4(), uuid4()
    await acquire_run(redis, user_id=user, project_id=project, now=60.0)
    assert int(await redis.get(_user_window(user, 1))) == 1
    assert int(await redis.get(_project_window(project, 1))) == 1
    assert int(await redis.get(_concurrency(user))) == 1


async def test_the_window_counters_expire_after_two_minutes(redis: Any) -> None:
    user, project = uuid4(), uuid4()
    await acquire_run(redis, user_id=user, project_id=project, now=60.0)
    assert await redis.ttl(_user_window(user, 1)) == 120
    assert await redis.ttl(_project_window(project, 1)) == 120


async def test_the_concurrency_counter_expires_after_an_hour(redis: Any) -> None:
    user, project = uuid4(), uuid4()
    await acquire_run(redis, user_id=user, project_id=project, now=60.0)
    assert await redis.ttl(_concurrency(user)) == 3600


async def test_the_minute_window_rolls_over_on_the_minute(redis: Any) -> None:
    settings = AgentSettings(agent_max_runs_per_minute_per_user=1, agent_max_runs_per_minute_per_project=0)
    user, project = uuid4(), uuid4()
    await acquire_run(redis, user_id=user, project_id=project, now=60.0)
    same_minute = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=119.9)
    next_minute = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=120.0)
    assert same_minute.allowed is False
    assert same_minute.retry_after == 1  # 120 - 119.9 rounds down to the next whole second
    assert same_minute.reason == "rate"
    assert next_minute.allowed is True


async def test_a_user_limit_of_one_denies_once_one_run_has_started(redis: Any) -> None:
    settings = AgentSettings(agent_max_runs_per_minute_per_user=1, agent_max_runs_per_minute_per_project=0)
    user, project = uuid4(), uuid4()
    before = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=0.0)
    await acquire_run(redis, user_id=user, project_id=project, now=0.0)
    after = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=0.0)
    assert before.allowed is True
    assert after.allowed is False and after.reason == "rate"


async def test_a_project_limit_applies_across_its_members(redis: Any) -> None:
    settings = AgentSettings(agent_max_runs_per_minute_per_user=0, agent_max_runs_per_minute_per_project=1)
    first, second, project = uuid4(), uuid4(), uuid4()
    await acquire_run(redis, user_id=first, project_id=project, now=0.0)
    other = await check_rate_limit(redis, settings, user_id=second, project_id=project, now=0.0)
    elsewhere = await check_rate_limit(redis, settings, user_id=second, project_id=uuid4(), now=0.0)
    assert other.allowed is False and other.reason == "rate"
    assert other.retry_after == 60
    assert elsewhere.allowed is True


async def test_a_disabled_user_limit_still_checks_the_project_limit(redis: Any) -> None:
    settings = AgentSettings(agent_max_runs_per_minute_per_user=0, agent_max_runs_per_minute_per_project=1)
    user, project = uuid4(), uuid4()
    await acquire_run(redis, user_id=user, project_id=project, now=0.0)
    decision = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=0.0)
    assert decision.allowed is False and decision.reason == "rate"


async def test_a_disabled_project_limit_allows_any_number_of_runs(redis: Any) -> None:
    settings = AgentSettings(
        agent_max_runs_per_minute_per_user=0,
        agent_max_runs_per_minute_per_project=0,
        agent_max_concurrent_runs_per_user=0,
    )
    user, project = uuid4(), uuid4()
    for _ in range(3):
        await acquire_run(redis, user_id=user, project_id=project, now=0.0)
    decision = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=0.0)
    assert decision.allowed is True


async def test_the_concurrency_cap_trips_exactly_at_the_limit(redis: Any) -> None:
    settings = AgentSettings(
        agent_max_runs_per_minute_per_user=0,
        agent_max_runs_per_minute_per_project=0,
        agent_max_concurrent_runs_per_user=2,
    )
    user, project = uuid4(), uuid4()
    await acquire_run(redis, user_id=user, project_id=project, now=0.0)
    one_running = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=0.0)
    await acquire_run(redis, user_id=user, project_id=project, now=0.0)
    two_running = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=0.0)
    assert one_running.allowed is True
    assert two_running.allowed is False
    assert two_running.retry_after == 5
    assert two_running.reason == "concurrency"


async def test_a_concurrency_denial_is_the_only_refusal_reason_for_that_user(redis: Any) -> None:
    settings = AgentSettings(
        agent_max_runs_per_minute_per_user=0,
        agent_max_runs_per_minute_per_project=0,
        agent_max_concurrent_runs_per_user=1,
    )
    busy, idle, project = uuid4(), uuid4(), uuid4()
    await acquire_run(redis, user_id=busy, project_id=project, now=0.0)
    refused = await check_rate_limit(redis, settings, user_id=busy, project_id=project, now=0.0)
    allowed = await check_rate_limit(redis, settings, user_id=idle, project_id=project, now=0.0)
    assert refused.allowed is False and refused.reason == "concurrency"
    assert allowed.allowed is True and allowed.reason == ""


async def test_a_disabled_concurrency_cap_allows_any_number_of_running_runs(redis: Any) -> None:
    settings = AgentSettings(
        agent_max_runs_per_minute_per_user=0,
        agent_max_runs_per_minute_per_project=0,
        agent_max_concurrent_runs_per_user=0,
    )
    user, project = uuid4(), uuid4()
    for _ in range(5):
        await acquire_run(redis, user_id=user, project_id=project, now=0.0)
    decision = await check_rate_limit(redis, settings, user_id=user, project_id=project, now=0.0)
    assert decision.allowed is True


async def test_check_rate_limit_does_not_bump_the_counters(redis: Any) -> None:
    settings = AgentSettings(agent_max_runs_per_minute_per_user=5)
    user, project = uuid4(), uuid4()
    await check_rate_limit(redis, settings, user_id=user, project_id=project, now=0.0)
    assert await redis.get(_user_window(user, 0)) is None


async def test_release_run_frees_one_slot(redis: Any) -> None:
    user, project = uuid4(), uuid4()
    await acquire_run(redis, user_id=user, project_id=project, now=0.0)
    await acquire_run(redis, user_id=user, project_id=project, now=0.0)
    await release_run(redis, user_id=user)
    assert int(await redis.get(_concurrency(user))) == 1


async def test_release_run_never_drives_the_counter_below_zero(redis: Any) -> None:
    user = uuid4()
    await release_run(redis, user_id=user)  # no counter yet: nothing to release, nothing created
    assert await redis.get(_concurrency(user)) is None
    await redis.set(_concurrency(user), 0)
    await release_run(redis, user_id=user)
    assert int(await redis.get(_concurrency(user))) == 0
