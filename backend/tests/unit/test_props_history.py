"""Property tests for the history version model (spec 36, spec 37). Pure: no database.

The chunk replay of ``reconstruct_doc`` is reproduced on in-memory replicas (``doc_from`` and
``YDocument``) so the properties run in milliseconds. The seeded-document case (commit 5548812) is
covered by making the random initial text part of the chunk base.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.history.versions.capture_values import doc_from
from inkstave.modules.history.versions.diff import apply_hunks, diff_text

_TEXT = st.text(alphabet="ab \n\\é世", max_size=30)
_INSERT = st.text(alphabet="xy\n é", max_size=4)


def _random_edit(data: st.DataObject, current: str) -> tuple[int, int, str]:
    start = data.draw(st.integers(0, len(current)))
    end = data.draw(st.integers(start, min(len(current), start + 4)))
    return start, end, data.draw(_INSERT)


def _capture_history(data: st.DataObject, initial: str) -> tuple[bytes, list[bytes], list[str], YDocument]:
    """Seed a document, then record each edit that changes its text as one history update."""
    live = YDocument()
    live.replace_text(initial)  # content present before the first captured edit
    base = live.get_state()
    updates: list[bytes] = []
    live.observe(lambda update, _origin: updates.append(update))
    texts = [live.text]
    for _ in range(data.draw(st.integers(0, 10))):
        before = len(updates)
        live.apply_edits([_random_edit(data, live.text)])
        if len(updates) > before:
            texts.append(live.text)
    return base, updates, texts, live


@given(initial=_TEXT, data=st.data())
def test_every_version_reconstructs_to_its_text(initial: str, data: st.DataObject) -> None:
    base, updates, texts, _live = _capture_history(data, initial)
    assert len(texts) == len(updates) + 1
    for version, expected in enumerate(texts):
        replica = doc_from(base)
        for update in updates[:version]:
            replica.apply_update(update)
        assert replica.text == expected


@given(initial=_TEXT, data=st.data())
def test_restoring_a_version_then_diffing_against_it_is_empty(initial: str, data: st.DataObject) -> None:
    _base, _updates, texts, live = _capture_history(data, initial)
    current = live.text
    for version_text in texts:
        restored = doc_from(live.get_state())
        restored.replace_text(version_text)  # what a restore writes into the live document
        assert restored.text == version_text
        assert diff_text(version_text, restored.text) == []
        assert apply_hunks(current, diff_text(current, version_text)) == version_text


@given(initial=_TEXT, data=st.data())
def test_an_update_that_changes_nothing_changes_no_state(initial: str, data: st.DataObject) -> None:
    base, updates, _texts, live = _capture_history(data, initial)
    replica = doc_from(base)
    for update in updates:
        replica.apply_update(update)
    settled = replica.get_state()
    for update in updates:  # a re-delivered update
        replica.apply_update(update)
    assert replica.get_state() == settled
    # the empty sync step an editor sends on connect: the peer's missing diff is empty
    replica.apply_update(live.diff(replica.get_state_vector()))
    assert replica.get_state() == settled
