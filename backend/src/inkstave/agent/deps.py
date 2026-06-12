"""Injected dependencies for the agent graph (spec 41, extended in spec 42)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from inkstave.agent.llm.base import LLMClient
from inkstave.agent.settings import AgentSettings
from inkstave.agent.tools.base import ToolContext, ToolRegistry

if TYPE_CHECKING:
    from inkstave.agent.api.events import EventSink


@dataclass(frozen=True)
class AgentDeps:
    """Everything the graph/nodes need, injected so nothing is hard-wired.

    ``tools`` is an empty registry in spec 41; spec 42 supplies the populated one.
    ``tool_context`` is set per-turn by the runner (it holds the DB session + the
    session's project/user scope); ``None`` means the act node has no tools to run.
    ``events``/``should_cancel`` (spec 44) let nodes stream events and stop on cancel;
    both ``None`` outside a streamed run.
    """

    llm: LLMClient
    settings: AgentSettings
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    tool_context: ToolContext | None = None
    events: EventSink | None = None
    should_cancel: Callable[[], Awaitable[bool]] | None = None
    # Safety (spec 49): per-run budget caps + injection framing. 0 / False disables.
    injection_guard: bool = True
    run_token_budget: int = 0
    run_cost_budget_usd: float = 0.0
    cost_per_1k: float = 0.0
