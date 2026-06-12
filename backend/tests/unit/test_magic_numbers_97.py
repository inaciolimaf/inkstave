"""No-value-drift guards for the named constants extracted in spec 97.

These lock the budget TTL/day-bucket and the section-locate score tiers to their
exact prior literals, so the "named, not retuned" invariant can't silently break.
The behavioural coverage lives in the existing budget/locate unit tests, which
pass unchanged.
"""

from __future__ import annotations

from inkstave.agent.context import locate
from inkstave.agent.safety.budget import _BUDGET_KEY_TTL_SECONDS, _SECONDS_PER_DAY


def test_budget_constants_match_original_literals() -> None:
    assert _SECONDS_PER_DAY == 86400
    assert _BUDGET_KEY_TTL_SECONDS == 172800
    assert _BUDGET_KEY_TTL_SECONDS == 2 * _SECONDS_PER_DAY  # derived from one source


def test_locate_score_tiers_match_original_literals() -> None:
    assert locate._SCORE_LABEL_MATCH == 0.95
    assert locate._SCORE_ORDINAL == 0.92
    assert locate._SCORE_SYNONYM == 0.9
    assert locate._SCORE_SUBSTRING == 0.7
    assert locate._SCORE_TOKEN_OVERLAP == 0.6
    # Strongest → weakest ordering is what drives the ranking sort.
    assert (
        locate._SCORE_LABEL_MATCH
        > locate._SCORE_ORDINAL
        > locate._SCORE_SYNONYM
        > locate._SCORE_SUBSTRING
        > locate._SCORE_TOKEN_OVERLAP
    )
