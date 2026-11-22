"""Property tests for the line diff behind history and the agent's proposals (spec 37). Pure."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from inkstave.modules.history.versions.diff import apply_hunks, diff_text

_LINES = st.text(alphabet="ab \n\\é\r", max_size=60)


@given(a=_LINES, b=_LINES)
def test_applying_every_hunk_turns_a_into_b_and_back(a: str, b: str) -> None:
    assert apply_hunks(a, diff_text(a, b)) == b
    assert apply_hunks(b, diff_text(b, a)) == a


@given(a=_LINES, b=_LINES)
def test_rejecting_every_hunk_keeps_a(a: str, b: str) -> None:
    diff_text(a, b)  # the hunks exist, but none is applied
    assert apply_hunks(a, []) == a


@given(a=_LINES, b=_LINES, data=st.data())
def test_any_subset_of_hunks_applies_without_error_and_deterministically(
    a: str, b: str, data: st.DataObject
) -> None:
    hunks = diff_text(a, b)
    subset = [hunk for hunk in hunks if data.draw(st.booleans())]
    first = apply_hunks(a, subset)
    assert isinstance(first, str)
    assert apply_hunks(a, subset) == first
