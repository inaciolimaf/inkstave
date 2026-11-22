"""Scenarios: the model gets the edit wrong, the system refuses it, and the model recovers.

Every run goes through the real graph, job and persistence. Nothing is written to a document
except through the user's own accept, so each scenario also checks the document is untouched.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.agent.scripted.steps import Call, Calls, Do, Reply, ScriptedLLM
from inkstave.modules.projects.content.documents import set_content_from_collab
from tests.agent_scenarios.support import (
    MAIN_TEX,
    NOTES_TEX,
    diffs_of,
    doc_text,
    final_text,
    make_project,
    new_session,
    play_turn,
    stored_tool_errors,
    tool_outcomes,
    transcript,
)

pytestmark = pytest.mark.integration


def read(doc: Any) -> Call:
    return Call("read_file", {"doc_id": str(doc)})


def edit(doc: Any, old: str, new: str) -> Call:
    return Call("propose_edit", {"doc_id": str(doc), "old_text": old, "new_text": new})


@pytest.fixture
async def project(db_session: AsyncSession) -> SimpleNamespace:
    return await make_project(db_session)


async def _assert_untouched(db: AsyncSession, project: SimpleNamespace) -> None:
    assert await doc_text(db, project, project.main_id) == MAIN_TEX
    assert await doc_text(db, project, project.notes_id) == NOTES_TEX


async def test_propose_without_reading_is_refused_then_the_model_reads_and_proposes(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    doc = project.main_id
    llm = ScriptedLLM(
        [
            Calls((edit(doc, "motivates", "MOTIVATES"),)),
            Calls((read(doc),)),
            Calls((edit(doc, "motivates", "MOTIVATES"),)),
            Reply("Done."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "tweak the intro")

    names = [(name, ok) for name, ok, _ in tool_outcomes(sink)]
    assert names == [("propose_edit", False), ("read_file", True), ("propose_edit", True)]
    assert "read_file this document" in tool_outcomes(sink)[0][2]
    # The model was shown the refusal before it tried again.
    assert any("read_file this document" in (m.content or "") for m in llm.calls[2])
    assert sink.events[-1]["type"] == "done"
    assert len(await diffs_of(db_session, session)) == 1
    await _assert_untouched(db_session, project)


async def test_old_text_not_found_is_returned_and_the_model_retries_with_the_exact_text(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    doc = project.main_id
    llm = ScriptedLLM(
        [
            Calls((read(doc),)),
            Calls((edit(doc, "The introduction explains the work.", "X"),)),
            Calls((edit(doc, "motivates", "MOTIVATES"),)),
            Reply("Done."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "tweak")

    refused = tool_outcomes(sink)[1]
    assert refused[1] is False and "not found" in refused[2]
    assert sink.events[-1]["type"] == "done"
    [diff] = await diffs_of(db_session, session)
    assert "+The introduction MOTIVATES the work." in diff.diff_text
    await _assert_untouched(db_session, project)


async def test_old_text_that_occurs_twice_is_refused_with_the_count(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    doc = project.main_id
    llm = ScriptedLLM(
        [
            Calls((read(doc),)),
            Calls((edit(doc, r"\section{", r"\chapter{"),)),
            Calls((edit(doc, r"\section{Methods}", r"\section{Results}"),)),
            Reply("Done."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "rename a section")

    refused = tool_outcomes(sink)[1]
    assert refused[1] is False and "occurs 2 times" in refused[2]
    [diff] = await diffs_of(db_session, session)
    assert r"+\section{Results}" in diff.diff_text and r"\chapter{" not in diff.diff_text
    await _assert_untouched(db_session, project)


async def test_a_collaborator_edit_between_read_and_propose_is_refused(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    doc = project.main_id
    note = "\n% a collaborator's note\n"

    async def collaborator_writes() -> None:
        await set_content_from_collab(db_session, doc, MAIN_TEX + note)
        await db_session.flush()

    llm = ScriptedLLM(
        [
            Calls((read(doc),)),
            Do(collaborator_writes, then=Calls((edit(doc, "motivates", "MOTIVATES"),))),
            Calls((read(doc),)),
            Calls((edit(doc, "motivates", "MOTIVATES"),)),
            Reply("Done."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "tweak")

    refused = tool_outcomes(sink)[1]
    assert refused[1] is False and "changed since you read it" in refused[2]
    [diff] = await diffs_of(db_session, session)
    # The proposal is made on the collaborator's text: their line stays, it is not reverted.
    assert "-% a collaborator" not in diff.diff_text
    assert "+The introduction MOTIVATES the work." in diff.diff_text
    assert await doc_text(db_session, project, doc) == MAIN_TEX + note


async def test_edits_to_two_files_in_one_run_make_one_proposal_each(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    main, notes = project.main_id, project.notes_id
    llm = ScriptedLLM(
        [
            Calls((read(main), read(notes))),
            Calls(
                (
                    edit(main, "motivates", "MOTIVATES"),
                    edit(notes, "cite the survey", "cite the survey and the benchmark"),
                )
            ),
            Reply("Done."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "tweak both")

    diffs = await diffs_of(db_session, session)
    assert {d.doc_id for d in diffs} == {main, notes}
    assert sorted(e["path"] for e in sink.events if e["type"] == "diff_proposed") == ["main.tex", "notes.tex"]
    assert sink.events[-1]["type"] == "done"
    await _assert_untouched(db_session, project)


async def test_two_edits_to_the_same_words_second_is_refused_then_one_combined_proposal(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    doc = project.main_id
    llm = ScriptedLLM(
        [
            Calls((read(doc),)),
            Calls(
                (
                    edit(doc, "motivates", "MOTIVATES"),
                    edit(doc, "motivates", "ENGAGES"),
                )
            ),
            Calls((edit(doc, "MOTIVATES", "ENGAGES"),)),
            Reply("Done."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "one place")

    outcomes = tool_outcomes(sink)
    assert [ok for _, ok, _ in outcomes[1:]] == [True, False, True]
    assert "not found" in outcomes[2][2]
    [diff] = await diffs_of(db_session, session)
    assert "+The introduction ENGAGES the work." in diff.diff_text
    assert "MOTIVATES" not in diff.diff_text
    await _assert_untouched(db_session, project)


async def test_propose_on_a_binary_or_missing_document_is_refused(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    llm = ScriptedLLM(
        [
            Calls(
                (
                    edit(project.binary_id, "a", "b"),
                    edit(uuid4(), "a", "b"),
                    read(project.binary_id),
                )
            ),
            Reply("That file cannot be edited as text."),
        ]
    )
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "edit the logo")

    assert [(ok, msg) for _, ok, msg in tool_outcomes(sink)] == [
        (False, "That file is not a text document."),
        (False, "No such document in this project."),
        (False, "That file is not a text document."),
    ]
    assert stored_tool_errors(await transcript(db_session, session)) == [
        "unsupported",
        "not_found",
        "unsupported",
    ]
    assert await diffs_of(db_session, session) == []
    assert final_text(sink) == "That file cannot be edited as text."
    await _assert_untouched(db_session, project)
