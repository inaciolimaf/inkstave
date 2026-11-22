"""Token estimate for agent context (spec 48). Deterministic.

The context selector that once packed chunks into a budget was removed: the model now
calls the context tools itself, so only the estimate is still used.
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """A deterministic token estimate (~4 chars/token). Swappable via DI."""
    return max(1, (len(text) + 3) // 4)
