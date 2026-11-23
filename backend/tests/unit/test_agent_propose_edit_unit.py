"""Unit tests for the propose_edit tool (spec 42): read guard, exact match, caps and staging.

The in-memory project is in `tests/fixtures/edit_world.py`; nothing here touches a database.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from inkstave.modules.agent.tools.base import ToolError
from inkstave.modules.agent.tools.propose_edit import ProposeEditArgs, ProposeEditTool
from inkstave.modules.agent.tools.read_file import ReadFileArgs, ReadFileTool
from tests.fixtures.edit_world import MAIN_TEXT, Doc, EditWorld


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> EditWorld:
    return EditWorld(monkeypatch)


async def _read(world: EditWorld, ctx: Any, doc: Any) -> None:
    await ReadFileTool().run(ReadFileArgs(doc_id=str(doc)), ctx)


async def _propose(world: EditWorld, ctx: Any, doc: Any, old: str, new: str, **kw: Any) -> Any:
    args = ProposeEditArgs(doc_id=str(doc), old_text=old, new_text=new, **kw)
    return await ProposeEditTool().run(args, ctx)


def _refused(result: Any, code: str = "invalid_args") -> bool:
    return not result.ok and result.error is not None and result.error.code == code


async def test_a_proposal_is_staged_and_the_document_is_untouched(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.main)
    result = await _propose(world, ctx, world.main, "alpha", "omega", rationale="clearer")

    assert result.ok and result.data is not None
    assert result.data["doc_id"] == str(world.main)
    assert result.data["path"] == "main.tex"
    assert result.data["base_version"] == "3"
    assert result.data["staged"] is True
    assert len(ctx.staged_edits) == 1
    edit = ctx.staged_edits[0]
    assert result.data["edit_id"] == edit.edit_id and len(edit.edit_id) == 32
    assert (edit.doc_id, edit.path, edit.base_version) == (str(world.main), "main.tex", "3")
    assert (edit.old_text, edit.new_text, edit.rationale) == ("alpha", "omega", "clearer")
    assert world.docs[world.main].content == MAIN_TEXT


async def test_a_proposal_without_a_read_is_refused(world: EditWorld) -> None:
    ctx = world.ctx()
    result = await _propose(world, ctx, world.main, "alpha", "omega")

    assert _refused(result)
    assert ctx.staged_edits == []


async def test_a_document_changed_since_the_read_is_refused(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.main)
    world.docs[world.main].version = 4

    result = await _propose(world, ctx, world.main, "alpha", "omega")
    assert _refused(result)
    assert ctx.staged_edits == []


async def test_reading_another_document_does_not_allow_an_edit(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.dup)
    assert _refused(await _propose(world, ctx, world.main, "alpha", "omega"))


async def test_old_text_must_occur_exactly_once(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.main)
    await _read(world, ctx, world.dup)

    assert _refused(await _propose(world, ctx, world.main, "zzz", "y"))
    assert _refused(await _propose(world, ctx, world.dup, "x", "y"))  # occurs twice: never guessed

    once = await _propose(world, ctx, world.dup, "x\nx", "y")
    assert once.ok
    assert len(ctx.staged_edits) == 1


async def test_an_empty_old_text_only_fills_an_empty_file(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.main)
    await _read(world, ctx, world.empty)

    assert _refused(await _propose(world, ctx, world.main, "", "new\n"))

    filled = await _propose(world, ctx, world.empty, "", "new\n")
    assert filled.ok and filled.data is not None
    assert ctx.staged_edits[-1].old_text == "" and ctx.staged_edits[-1].new_text == "new\n"


async def test_a_no_op_edit_is_refused(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.main)
    result = await _propose(world, ctx, world.main, "alpha", "alpha")

    assert _refused(result)
    assert ctx.staged_edits == []


async def test_text_over_the_edit_cap_is_refused_at_the_limit_and_above(world: EditWorld) -> None:
    ctx = world.ctx(edit_max=10)
    await _read(world, ctx, world.main)

    assert (await _propose(world, ctx, world.main, "alpha", "0123456789")).ok
    assert _refused(await _propose(world, ctx, world.main, "beta", "01234567890"))
    assert _refused(await _propose(world, ctx, world.main, "0123456789A", "x"))


async def test_old_text_exactly_at_the_edit_cap_is_accepted(world: EditWorld) -> None:
    world.docs[world.main] = Doc("0123456789 tail\n", 3)
    ctx = world.ctx(edit_max=10)
    await _read(world, ctx, world.main)

    assert (await _propose(world, ctx, world.main, "0123456789", "x")).ok


async def test_each_edit_applies_to_the_text_the_earlier_ones_left(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.main)
    first = await _propose(world, ctx, world.main, "alpha", "beta gamma")
    second = await _propose(world, ctx, world.main, "beta gamma", "delta")
    stale = await _propose(world, ctx, world.main, "alpha", "epsilon")

    assert first.ok and second.ok
    assert _refused(stale)
    assert [e.new_text for e in ctx.staged_edits] == ["beta gamma", "delta"]


async def test_a_read_after_a_proposal_shows_the_edited_text(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.main)
    await _propose(world, ctx, world.main, "alpha", "omega")

    result = await ReadFileTool().run(ReadFileArgs(doc_id=str(world.main)), ctx)
    assert result.ok and result.data is not None
    assert result.data["content"] == MAIN_TEXT.replace("alpha", "omega")
    assert result.data["proposed_edits"] == 1
    assert "note" in result.data


async def test_a_writer_check_is_made_for_the_edit(world: EditWorld) -> None:
    ctx = world.ctx()
    await _read(world, ctx, world.main)
    world.denied = ToolError(code="forbidden", message="read only")
    result = await _propose(world, ctx, world.main, "alpha", "omega")

    assert _refused(result, "forbidden")
    assert ctx.staged_edits == []
    assert world.auth_calls[-1]["require_write"] is True
    assert world.auth_calls[-1]["ctx"] is ctx


async def test_an_unknown_document_is_not_found(world: EditWorld) -> None:
    result = await _propose(world, world.ctx(), uuid4(), "alpha", "omega")
    assert _refused(result, "not_found")
