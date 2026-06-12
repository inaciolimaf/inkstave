"""Unit tests for agent state, prompts, import-isolation, and graph caps (spec 41)."""

from __future__ import annotations

import inspect
from pathlib import Path

from inkstave.agent import graph as graph_mod
from inkstave.agent import nodes as nodes_mod
from inkstave.agent.deps import AgentDeps
from inkstave.agent.graph import build_graph
from inkstave.agent.llm.base import LLMMessage, LLMResponse, LLMUsage, ToolCall
from inkstave.agent.llm.fake import FakeLLM
from inkstave.agent.prompts import PromptContext, build_system_prompt
from inkstave.agent.settings import AgentSettings
from inkstave.agent.state import AgentState, deserialize_state, serialize_state


def test_state_serialization_round_trips() -> None:
    state: AgentState = {
        "session_id": "s1",
        "project_id": "p1",
        "user_id": "u1",
        "messages": [
            LLMMessage(role="user", content="hi"),
            LLMMessage(role="assistant", content="hello"),
        ],
        "pending_tool_calls": [ToolCall(id="t1", name="search", arguments={"q": "x"})],
        "iterations": 2,
        "total_tokens": 10,
        "usage": LLMUsage(prompt=4, completion=6, total=10),
        "final_response": "hello",
        "error": None,
    }
    restored = deserialize_state(serialize_state(state))
    assert restored["session_id"] == "s1"
    assert [m.content for m in restored["messages"]] == ["hi", "hello"]
    assert restored["pending_tool_calls"][0].name == "search"
    assert restored["iterations"] == 2 and restored["total_tokens"] == 10
    assert restored["usage"].total == 10
    assert restored["final_response"] == "hello"


def test_system_prompt_states_no_direct_writes() -> None:
    # AC8: the prompt must say it never modifies files directly and proposes diffs.
    prompt = build_system_prompt(PromptContext(project_id="p1", project_name="Paper", file_count=3))
    lowered = prompt.lower()
    assert "never modify files directly" in lowered
    assert "diff" in lowered and "review" in lowered
    assert "Paper" in prompt


def test_nodes_and_graph_do_not_import_openai() -> None:
    # AC6: the LLM is reached only through the injected client.
    for module in (nodes_mod, graph_mod):
        source = Path(inspect.getfile(module)).read_text()
        assert "import openai" not in source
        assert "from openai" not in source


def test_only_openrouter_imports_openai() -> None:
    # Spec 45 AC2: no module in the agent package imports openai except the wrapper.
    import inkstave.agent as agent_pkg

    root = Path(agent_pkg.__file__).parent
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.name != "openrouter.py"
        and ("import openai" in (src := path.read_text()) or "from openai" in src)
    ]
    assert offenders == []


def _deps(script: list, **over: object) -> AgentDeps:
    settings = AgentSettings(**over)  # type: ignore[arg-type]
    return AgentDeps(llm=FakeLLM(script=script), settings=settings)


async def _run(deps: AgentDeps) -> AgentState:
    initial: AgentState = {
        "messages": [LLMMessage(role="user", content="hi")],
        "pending_tool_calls": [],
        "iterations": 0,
        "total_tokens": 0,
        "usage": LLMUsage(),
        "final_response": None,
        "error": None,
    }
    return await build_graph(deps).ainvoke(initial)  # type: ignore[return-value]


def _tool_response(_msgs: list[LLMMessage]) -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall(id="c1", name="ghost", arguments={})], finish_reason="tool_calls"
    )


async def test_hallucinated_tool_is_marked_unavailable_and_terminates() -> None:
    # AC4 (spec 41) / AC8 (spec 42): an unknown tool → `act` returns an `unsupported`
    # ToolResult; loop does not spin.
    deps = _deps([_tool_response])  # second plan call falls back to the default "stop"
    out = await _run(deps)
    roles = [m.role for m in out["messages"]]
    tool_msgs = [m for m in out["messages"] if m.role == "tool"]
    assert tool_msgs and "unsupported" in (tool_msgs[0].content or "")
    assert roles[-1] == "assistant"  # terminated via respond
    assert out["final_response"] is not None


async def test_tool_spam_stops_at_max_iterations() -> None:
    # AC5: a model that always calls a tool stops after max_iterations, no infinite loop.
    deps = _deps([_tool_response] * 50, agent_max_iterations=4)
    out = await _run(deps)
    assert out["iterations"] == 4  # capped
    assert out["final_response"] is not None
    assert out["messages"][-1].role == "assistant"
