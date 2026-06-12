"""Agent safety: rate limits, budgets, injection mitigation, audit logging (spec 49)."""

from inkstave.agent.safety.audit import audit
from inkstave.agent.safety.budget import (
    BudgetDecision,
    avg_rate_per_1k,
    cost_for,
    precheck_day,
    record_usage,
    run_cost_exceeded,
    run_tokens_exceeded,
)
from inkstave.agent.safety.injection import flag_injection, wrap_untrusted
from inkstave.agent.safety.models import AgentAuditAction, AgentAuditLog
from inkstave.agent.safety.rate_limit import (
    RateDecision,
    acquire_run,
    check_rate_limit,
    release_run,
)

__all__ = [
    "AgentAuditAction",
    "AgentAuditLog",
    "BudgetDecision",
    "RateDecision",
    "acquire_run",
    "audit",
    "avg_rate_per_1k",
    "check_rate_limit",
    "cost_for",
    "flag_injection",
    "precheck_day",
    "record_usage",
    "release_run",
    "run_cost_exceeded",
    "run_tokens_exceeded",
    "wrap_untrusted",
]
