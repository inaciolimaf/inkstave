"""Unit tests for the read_file tool (spec 42): resolution, windows, the char cap and the notes.

The in-memory project is in `tests/fixtures/edit_world.py`; nothing here touches a database.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from inkstave.modules.agent.graph.edits import StagedEdit
from inkstave.modules.agent.tools.base import ToolContext, ToolError
from inkstave.modules.agent.tools.read_file import ReadFileArgs, ReadFileTool, _cap_to_chars, _notes
from tests.fixtures.edit_world import MAIN_TEXT, THREE_LINES, Doc, EditWorld


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> EditWorld:
    return EditWorld(monkeypatch)


async def _read(ctx: ToolContext, **args: Any) -> Any:
    return await ReadFileTool().run(ReadFileArgs(**args), ctx)


async def test_read_by_doc_id_returns_the_whole_document(world: EditWorld) -> None:
    ctx = world.ctx()
    result = await _read(ctx, doc_id=str(world.main))

    assert result.ok
    assert result.data == {
        "doc_id": str(world.main),
        "path": "main.tex",
        "version": "3",
        "start_line": 0,
        "end_line": 4,
        "line_count": 4,
        "content": MAIN_TEXT,
        "truncated": False,
    }
    assert ctx.read_versions == {str(world.main): "3"}


async def test_read_by_path_finds_documents_and_only_documents(world: EditWorld) -> None:
    nested = await _read(world.ctx(), path="x/y.tex")
    assert nested.ok and nested.data is not None
    assert nested.data["doc_id"] == str(world.nested)
    assert nested.data["path"] == "x/y.tex"

    folder = await _read(world.ctx(), path="x")
    assert not folder.ok and folder.error is not None and folder.error.code == "not_found"

    missing = await _read(world.ctx(), path="missing.tex")
    assert not missing.ok and missing.error is not None and missing.error.code == "not_found"


async def test_unknown_or_malformed_ids_are_not_found(world: EditWorld) -> None:
    for doc_id in (str(uuid4()), "not-a-uuid"):
        result = await _read(world.ctx(), doc_id=doc_id)
        assert not result.ok and result.error is not None and result.error.code == "not_found"


async def test_a_folder_is_not_a_readable_document(world: EditWorld) -> None:
    result = await _read(world.ctx(), doc_id=str(world.folder))
    assert not result.ok and result.error is not None and result.error.code == "unsupported"


async def test_a_reader_without_access_gets_no_content(world: EditWorld) -> None:
    world.denied = ToolError(code="forbidden", message="no access")
    ctx = world.ctx()
    result = await _read(ctx, doc_id=str(world.main))

    assert not result.ok and result.error is not None and result.error.code == "forbidden"
    assert ctx.read_versions == {}
    assert world.auth_calls[0]["ctx"] is ctx


async def test_window_selects_the_half_open_line_range(world: EditWorld) -> None:
    cases = [
        ({"start_line": 1, "end_line": 3}, 1, 3, "two\nthree\n"),
        ({"start_line": 2}, 2, 3, "three\n"),
        ({"end_line": 2}, 0, 2, "one\ntwo\n"),
        ({"start_line": 0}, 0, 3, THREE_LINES),
        ({"start_line": 0, "end_line": 0}, 0, 0, ""),
        ({"start_line": 3}, 3, 3, ""),
    ]
    for window, start, end, content in cases:
        result = await _read(world.ctx(), doc_id=str(world.nested), **window)
        assert result.ok, window
        assert result.data is not None
        got = (result.data["start_line"], result.data["end_line"], result.data["content"])
        assert got == (start, end, content), window
        assert result.data["line_count"] == 3
        assert result.data["truncated"] is False


async def test_a_window_starting_past_the_end_is_refused(world: EditWorld) -> None:
    result = await _read(world.ctx(), doc_id=str(world.nested), start_line=4)
    assert not result.ok and result.error is not None and result.error.code == "invalid_args"


async def test_the_char_cap_keeps_whole_lines_and_says_so(world: EditWorld) -> None:
    world.docs[world.nested] = Doc("aaa\nbbb\nccc\n", 0)
    result = await _read(world.ctx(read_max=8), doc_id=str(world.nested))

    assert result.ok and result.data is not None
    assert result.data["content"] == "aaa\nbbb\n"
    assert result.data["end_line"] == 2
    assert result.data["line_count"] == 3
    assert result.data["truncated"] is True
    assert "hint" in result.data
    assert "proposed_edits" not in result.data


async def test_the_char_cap_applies_to_a_window_too(world: EditWorld) -> None:
    world.docs[world.nested] = Doc("aaa\nbbb\nccc\n", 0)
    result = await _read(world.ctx(read_max=4), doc_id=str(world.nested), start_line=1)

    assert result.ok and result.data is not None
    assert result.data["content"] == "bbb\n"
    assert (result.data["start_line"], result.data["end_line"]) == (1, 2)
    assert result.data["truncated"] is True


def test_cap_keeps_whole_lines_within_the_cap() -> None:
    lines = ["ab\n", "cd\n", "ef\n"]
    assert _cap_to_chars(lines, 6) == ("ab\ncd\n", 2, True)
    assert _cap_to_chars(lines, 8) == ("ab\ncd\n", 2, True)
    assert _cap_to_chars(lines, 9) == ("ab\ncd\nef\n", 3, False)


def test_cap_of_no_lines_is_empty_and_not_truncated() -> None:
    assert _cap_to_chars([], 5) == ("", 0, False)


def test_a_first_line_longer_than_the_cap_is_cut() -> None:
    assert _cap_to_chars(["abcdefgh\n", "x\n"], 4) == ("abcd", 1, True)


def test_a_single_line_that_fits_is_kept_whole() -> None:
    assert _cap_to_chars(["ab\n"], 3) == ("ab\n", 1, False)
    assert _cap_to_chars(["ab\n"], 2) == ("ab", 1, True)


def _staged(doc_id: str, old: str, new: str) -> StagedEdit:
    return StagedEdit(
        edit_id=uuid4().hex, doc_id=doc_id, path="f.tex", base_version="1", old_text=old, new_text=new
    )


def test_notes_are_empty_without_edits_or_truncation(world: EditWorld) -> None:
    assert _notes(world.ctx(), str(world.main), False) == {}


def test_notes_count_only_this_documents_edits(world: EditWorld) -> None:
    ctx = world.ctx()
    doc = str(world.main)
    ctx.staged_edits.extend([_staged(doc, "a", "b"), _staged(doc, "b", "c"), _staged("other", "x", "y")])
    notes = _notes(ctx, doc, False)

    assert set(notes) == {"proposed_edits", "note"}
    assert notes["proposed_edits"] == 2
    assert isinstance(notes["note"], str) and notes["note"]


def test_notes_flag_a_truncated_read(world: EditWorld) -> None:
    notes = _notes(world.ctx(), str(world.main), True)
    assert set(notes) == {"hint"}
    assert isinstance(notes["hint"], str) and notes["hint"]
