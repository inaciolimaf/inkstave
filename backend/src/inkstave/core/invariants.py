"""Runtime invariant guards that survive ``python -O``.

``assert`` is the natural way to spell "this cannot be None here", but it is
stripped under ``python -O`` and is banned by lint rule ``S101`` precisely
because that turns a guard into nothing. Where the invariant protects real data
— a history row with neither an inline payload nor a blob key, say — use these
helpers instead: they raise unconditionally and narrow the type for mypy.
"""

from __future__ import annotations


class InvariantError(RuntimeError):
    """An internal invariant did not hold — a bug or corrupt data, never user input."""


def require[T](value: T | None, message: str) -> T:
    """Return `value`, raising :class:`InvariantError` if it is ``None``."""
    if value is None:
        raise InvariantError(message)
    return value
