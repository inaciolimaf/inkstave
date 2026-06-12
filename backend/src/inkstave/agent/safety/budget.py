"""Token/cost budgets per run and per day (spec 49). Cost = tokens × configured rate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.agent.settings import AgentSettings

_DEFAULT_RATE = {"input": 0.00015, "output": 0.0006}  # USD per 1K tokens

_SECONDS_PER_DAY = 86_400  # day-bucket granularity for per-day usage counters
# Daily counters live one extra day past their bucket so late roll-ups still land.
_BUDGET_KEY_TTL_SECONDS = 2 * _SECONDS_PER_DAY  # == 172_800 (2-day grace TTL)


def model_rates(settings: AgentSettings, model: str) -> dict[str, float]:
    table = settings.agent_model_cost_table
    return table.get(model, next(iter(table.values()), _DEFAULT_RATE))


def cost_for(settings: AgentSettings, model: str, prompt: int, completion: int) -> Decimal:
    rates = model_rates(settings, model)
    return Decimal(prompt) / 1000 * Decimal(str(rates["input"])) + Decimal(
        completion
    ) / 1000 * Decimal(str(rates["output"]))


def avg_rate_per_1k(settings: AgentSettings, model: str) -> float:
    rates = model_rates(settings, model)
    return (rates["input"] + rates["output"]) / 2


def run_tokens_exceeded(total_tokens: int, settings: AgentSettings) -> bool:
    cap = settings.agent_max_tokens_per_run
    return cap > 0 and total_tokens >= cap


def run_cost_exceeded(cost_usd: float, settings: AgentSettings) -> bool:
    cap = settings.agent_max_cost_per_run_usd
    return cap > 0 and cost_usd >= cap


@dataclass
class BudgetDecision:
    allowed: bool
    reason: str = ""


def _day(now: float) -> int:
    return int(now) // _SECONDS_PER_DAY


def _proj_tokens_key(project_id: UUID, day: int) -> str:
    return f"agent:day:proj:{project_id}:{day}:tokens"


def _user_cost_key(user_id: UUID, day: int) -> str:
    return f"agent:day:user:{user_id}:{day}:microusd"


async def precheck_day(
    redis: Redis, settings: AgentSettings, *, user_id: UUID, project_id: UUID, now: float
) -> BudgetDecision:
    """Refuse before any LLM call if a per-day cap is already exhausted."""
    day = _day(now)
    proj_cap = settings.agent_max_tokens_per_day_per_project
    if proj_cap > 0:
        used = await redis.get(_proj_tokens_key(project_id, day))
        if used is not None and int(used) >= proj_cap:
            return BudgetDecision(False, "project_day_tokens")

    user_cap = settings.agent_max_cost_per_day_per_user_usd
    if user_cap > 0:
        used = await redis.get(_user_cost_key(user_id, day))
        if used is not None and Decimal(int(used)) / 1_000_000 >= Decimal(str(user_cap)):
            return BudgetDecision(False, "user_day_cost")

    return BudgetDecision(True)


async def record_usage(
    redis: Redis,
    *,
    user_id: UUID,
    project_id: UUID,
    now: float,
    tokens: int,
    cost: Decimal,
) -> None:
    """Roll up a finished run's tokens + cost into the per-day counters (2-day TTL)."""
    day = _day(now)
    tkey = _proj_tokens_key(project_id, day)
    await redis.incrby(tkey, tokens)
    await redis.expire(tkey, _BUDGET_KEY_TTL_SECONDS)
    ckey = _user_cost_key(user_id, day)
    await redis.incrby(ckey, int(cost * 1_000_000))
    await redis.expire(ckey, _BUDGET_KEY_TTL_SECONDS)
