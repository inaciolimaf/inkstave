"""Spec 121: the three-way text merge of a Git push into the live document, and its CRDT application."""

from __future__ import annotations

import random

from pycrdt import Doc, Text

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.git.push.textmerge import plan_text_edits


def _apply(live: str, edits: list) -> str:  # type: ignore[type-arg]
    """Apply the planner's edits the way the CRDT does: from the end, character offsets."""
    text = live
    for edit in edits:
        text = text[: edit.start] + edit.text + text[edit.end :]
    return text


def test_identical_push_plans_nothing() -> None:
    edits, conflicts = plan_text_edits("a\nb\n", "a\nb\n", "a\nb\n")
    assert edits == [] and conflicts == []


def test_push_of_a_changed_line_becomes_one_minimal_edit() -> None:
    old = "one\ntwo\nthree\n"
    new = "one\n2\nthree\n"
    edits, conflicts = plan_text_edits(old, old, new)
    assert conflicts == []
    assert _apply(old, edits) == new
    # The change is "two" -> "2", so the edit covers the word and nothing else.
    assert len(edits) == 1 and edits[0].text == "2"


def test_collaborator_lines_above_the_hunk_survive() -> None:
    old = "alpha\nbeta\ngamma\n"
    live = "NEW TOP\nalpha\nbeta\ngamma\n"  # a collaborator added a line above
    new = "alpha\nBETA\ngamma\n"  # the pusher changed beta
    edits, conflicts = plan_text_edits(live, old, new)
    assert conflicts == []
    assert _apply(live, edits) == "NEW TOP\nalpha\nBETA\ngamma\n"


def test_collaborator_edit_in_another_region_survives() -> None:
    old = "one\ntwo\nthree\nfour\n"
    live = "one\ntwo\nTHREE\nfour\n"  # collaborator changed line three
    new = "one\n2\nthree\nfour\n"  # pusher changed line two
    edits, conflicts = plan_text_edits(live, old, new)
    assert conflicts == []
    assert _apply(live, edits) == "one\n2\nTHREE\nfour\n"


def test_overlapping_edit_is_applied_and_reported() -> None:
    old = "keep\nshared line\nkeep too\n"
    live = "keep\nthe collaborator's line\nkeep too\n"
    new = "keep\npushed line\nkeep too\n"
    edits, conflicts = plan_text_edits(live, old, new)
    assert _apply(live, edits) == "keep\npushed line\nkeep too\n"
    assert len(conflicts) == 1
    assert (conflicts[0].first_line, conflicts[0].last_line) == (2, 2)


def test_insertion_and_deletion_in_one_push() -> None:
    old = "a\nb\nc\nd\n"
    new = "a\nc\nX\nd\n"  # b deleted, X inserted before d
    live = "a\nb\nc\nd\n"
    edits, conflicts = plan_text_edits(live, old, new)
    assert conflicts == []
    assert _apply(live, edits) == new


def test_non_ascii_offsets_are_characters_in_the_planner() -> None:
    old = "é 😀 end\nline\n"
    live = "é 😀 end\nline\n"
    new = "é 😀 done\nline\n"
    edits, _ = plan_text_edits(live, old, new)
    assert _apply(live, edits) == new


def test_random_edits_always_converge_to_the_pushed_text() -> None:
    rng = random.Random(121)
    words = ["alpha", "beta", "γ", "😀", "x y", ""]
    for _ in range(200):
        old = "".join(rng.choice(words) + "\n" for _ in range(rng.randint(0, 6)))
        new = "".join(rng.choice(words) + "\n" for _ in range(rng.randint(0, 6)))
        # The live text equals the base when nobody else edited: then the push must land exactly.
        edits, conflicts = plan_text_edits(old, old, new)
        assert conflicts == []
        assert _apply(old, edits) == new


def test_crdt_edits_round_trip_through_pycrdt_utf8_offsets() -> None:
    doc = YDocument()
    doc.replace_text("a 😀 b\nsecond\n")
    live = doc.text
    edits, _ = plan_text_edits(live, live, "a 😀 B\nsecond\nthird\n")
    doc.apply_edits([(e.start, e.end, e.text) for e in edits])
    assert doc.text == "a 😀 B\nsecond\nthird\n"


def test_pycrdt_counts_utf8_bytes_so_the_helper_must_convert() -> None:
    # Documents the pitfall apply_edits guards against: a character offset past an emoji is not the
    # same position in pycrdt, which counts UTF-8 bytes.
    raw = Doc()
    text = raw.get("content", type=Text)
    text.insert(0, "😀b")
    text.insert(4, "X")  # byte offset 4 is right before "b"
    assert str(text) == "😀Xb"
