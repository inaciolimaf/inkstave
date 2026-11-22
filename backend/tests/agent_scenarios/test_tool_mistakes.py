"""Scenarios: the model calls a tool wrongly (bad arguments, a made-up id or tool, broken JSON, a loop).

The tool error goes back to the model as a result, the model gets its next step, and the run ends in
the state its turn deserves. Nothing is written to a document.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.llm.base import LLMMessage
from inkstave.modules.agent.scripted.steps import Call, Calls, Reply, ScriptedLLM
from tests.agent_scenarios.support import (
    MAIN_TEX,
    diffs_of,
    doc_text,
    final_text,
    make_project,
    new_session,
    play_turn,
    stored_tool_errors,
    tool_outcomes,
    transcript,
    unanswered_tool_calls,
)

pytestmark = pytest.mark.integration

CAPPED_MARK = "stopped before finishing"


@pytest.fixture
async def project(db_session: AsyncSession) -> SimpleNamespace:
    return await make_project(db_session)


def read(doc: Any) -> Call:
    return Call("read_file", {"doc_id": str(doc)})


async def _next_turn_history(db: AsyncSession, redis: Any, session: Any) -> list[LLMMessage]:
    """The transcript the model is shown on the next message of the same session."""
    llm = ScriptedLLM([Reply("Sure.")])
    await play_turn(db, redis, session, llm, "and now?")
    return llm.calls[0]


async def test_invalid_arguments_come_back_as_invalid_args_and_the_model_recovers(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    doc = project.main_id
    llm = ScriptedLLM(
        [
            # propose_edit without new_text: a pydantic error, not a crash.
            Calls((Call("propose_edit", {"doc_id": str(doc), "old_text": "motivates"}),)),
            Calls((read(doc),)),
            Calls((Call("propose_edit", {"doc_id": str(doc), "old_text": "motivates", "new_text": "M"}),)),
            Reply("Done."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "tweak")

    assert [(n, ok) for n, ok, _ in tool_outcomes(sink)] == [
        ("propose_edit", False),
        ("read_file", True),
        ("propose_edit", True),
    ]
    assert any("new_text" in (m.content or "") for m in llm.calls[1])  # the model saw the field error
    assert sink.events[-1]["type"] == "done"
    assert len(await diffs_of(db_session, session)) == 1
    assert await doc_text(db_session, project, doc) == MAIN_TEX


async def test_unknown_document_id_is_not_found_and_the_model_searches_instead(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    llm = ScriptedLLM(
        [
            Calls((read(uuid4()),)),
            Calls((Call("search_project", {"query": "Introduction"}),)),
            Reply("I could not find that file, but the introduction is in main.tex."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "read it")

    assert tool_outcomes(sink)[0][1] is False and tool_outcomes(sink)[0][2].startswith("No such document")
    assert tool_outcomes(sink)[1][1] is True
    assert stored_tool_errors(await transcript(db_session, session)) == ["not_found"]
    assert sink.events[-1]["type"] == "done"


async def test_a_tool_that_does_not_exist_is_refused_and_the_run_goes_on(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    llm = ScriptedLLM(
        [
            Calls((Call("rewrite_whole_project", {"instructions": "make it shorter"}),)),
            Calls((read(project.main_id),)),
            Reply("I can only read and propose edits; nothing was changed."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "shorten everything")

    first = tool_outcomes(sink)[0]
    assert first[1] is False and first[2] == "unknown tool: rewrite_whole_project"
    assert [ok for _, ok, _ in tool_outcomes(sink)[1:]] == [True]
    assert sink.events[-1]["type"] == "done"
    assert await diffs_of(db_session, session) == []
    assert await doc_text(db_session, project, project.main_id) == MAIN_TEX


async def test_malformed_json_arguments_come_back_as_invalid_args(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    llm = ScriptedLLM(
        [
            Calls((Call("read_file", raw='{"doc_id": "'),)),
            Calls((read(project.main_id),)),
            Reply("Here is the introduction."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "show intro")

    assert [(n, ok) for n, ok, _ in tool_outcomes(sink)] == [("read_file", False), ("read_file", True)]
    assert stored_tool_errors(await transcript(db_session, session)) == ["invalid_args"]
    assert final_text(sink) == "Here is the introduction."
    assert sink.events[-1]["type"] == "done"


async def test_a_model_stuck_in_a_loop_is_stopped_at_the_step_cap(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    settings = AgentSettings(agent_max_iterations=3)
    loop = ScriptedLLM([], tail=Calls((read(project.main_id),)))
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, loop, "keep reading", settings=settings)

    # Three model calls: the third is the cap, so only the first two calls run their tool.
    assert sum(1 for e in sink.events if e["type"] == "tool_call") == 2
    assert CAPPED_MARK in final_text(sink)
    assert sink.events[-1]["type"] == "done"
    assert await diffs_of(db_session, session) == []


@pytest.mark.xfail(reason="known bug: a cancelled tool call stays in the history (fixed next)", strict=True)
async def test_the_next_message_after_a_capped_loop_sends_a_valid_history(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    """A capped turn stores its last tool call with no result; the next turn must not replay that."""
    settings = AgentSettings(agent_max_iterations=3)
    loop = ScriptedLLM([], tail=Calls((read(project.main_id),)))
    session = await new_session(db_session, project)
    await play_turn(db_session, redis, session, loop, "keep reading", settings=settings)

    history = await _next_turn_history(db_session, redis, session)
    assert unanswered_tool_calls(history) == []
