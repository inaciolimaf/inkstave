"""The named scenarios of the e2e stub (``LLM_STUB_SCENARIO``), run through the real job.

The e2e flows rely on each name meaning what it says: a recoverable mistake ends in a reviewable
proposal, a provider failure ends in an error. These runs pin that, with no browser involved.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.agent.llm.stub import StubAgentLLM
from inkstave.modules.agent.scripted.scenarios import SCENARIO_NAMES
from tests.agent_scenarios.support import (
    MAIN_TEX,
    NOTES_TEX,
    diffs_of,
    doc_text,
    make_project,
    new_session,
    play_turn,
)

pytestmark = pytest.mark.integration

# scenario -> the run's end: "done" with a proposal, or "error" with none
EXPECTED: dict[str, str] = {
    "happy": "done",
    "propose_without_read": "done",
    "old_text_not_found": "done",
    "malformed_arguments": "done",
    "unknown_tool": "done",
    "empty_reply": "error",
    "provider_error": "error",
    "stream_cut": "error",
}


def test_every_scenario_name_has_an_expected_end() -> None:
    assert set(EXPECTED) == set(SCENARIO_NAMES)


def test_an_unknown_scenario_name_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown LLM_STUB_SCENARIO"):
        StubAgentLLM(scenario="no_such_scenario")


@pytest.mark.parametrize("name", SCENARIO_NAMES)
async def test_a_stub_scenario_ends_as_its_name_says(name: str, db_session: AsyncSession, redis: Any) -> None:
    project: SimpleNamespace = await make_project(db_session)
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, StubAgentLLM(scenario=name), "rewrite the intro")

    assert sink.events[-1]["type"] == EXPECTED[name]
    diffs = await diffs_of(db_session, session)
    assert len(diffs) == (1 if EXPECTED[name] == "done" else 0)
    assert await doc_text(db_session, project, project.main_id) == MAIN_TEX
    assert await doc_text(db_session, project, project.notes_id) == NOTES_TEX
