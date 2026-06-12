"""LangGraph assembly for the agent (spec 41).

``plan`` loops through ``act → observe → plan`` while there is more tool work and
safety caps allow, then routes to ``respond``. Reaches the model only via the
injected ``LLMClient`` — this module never imports ``openai``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from langgraph.graph import END, START, StateGraph

from inkstave.agent.nodes import make_act, make_observe, make_plan, make_respond
from inkstave.agent.state import AgentState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from inkstave.agent.deps import AgentDeps


def _make_router(deps: AgentDeps):
    settings = deps.settings

    def route_after_plan(state: AgentState) -> Literal["act", "respond"]:
        if state.get("error"):
            return "respond"
        if not state.get("pending_tool_calls"):
            return "respond"
        if state.get("iterations", 0) >= settings.agent_max_iterations:
            return "respond"
        if state.get("total_tokens", 0) >= settings.agent_max_total_tokens:
            return "respond"
        return "act"

    return route_after_plan


def build_graph(deps: AgentDeps) -> CompiledStateGraph:
    builder: StateGraph = StateGraph(AgentState)
    builder.add_node("plan", make_plan(deps))
    builder.add_node("act", make_act(deps))
    builder.add_node("observe", make_observe(deps))
    builder.add_node("respond", make_respond(deps))

    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", _make_router(deps), {"act": "act", "respond": "respond"})
    builder.add_edge("act", "observe")
    builder.add_edge("observe", "plan")
    builder.add_edge("respond", END)

    return builder.compile()
