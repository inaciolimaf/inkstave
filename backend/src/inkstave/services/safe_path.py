"""Path-segment validation for tree-entity names (spec 12).

Reimplements the *rules* of Overleaf's SafePath independently: a name is a single
path segment, free of traversal/separators/control characters and
Windows-hostile forms. Reused by specs 13/14. Names are stored as given (after a
surrounding-whitespace strip); uniqueness is enforced case-insensitively at the
DB layer.
"""

from __future__ import annotations

from collections.abc import Callable

from inkstave.errors import AppError

MAX_TREE_ENTITY_NAME_LENGTH = 255

# Windows reserved device names (matched case-insensitively, on the stem).
_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class InvalidNameError(AppError):
    """A tree-entity name failed path-safety validation."""

    status_code = 422
    error_type = "invalid_name"

    def __init__(self, message: str = "Invalid name.") -> None:
        super().__init__(message)


def _is_reserved(name: str) -> bool:
    """Windows device names are rejected bare and as a file stem (``con.txt``)."""
    stem = name.split(".", 1)[0]
    return name.lower() in _RESERVED_NAMES or stem.lower() in _RESERVED_NAMES


# Each rule rejects a name when its predicate holds; checked in order.
_NAME_RULES: tuple[tuple[Callable[[str], bool], str], ...] = (
    (lambda n: not n, "Name must not be empty."),
    (lambda n: len(n) > MAX_TREE_ENTITY_NAME_LENGTH, "Name is too long."),
    (lambda n: "/" in n or "\\" in n, "Name must not contain a path separator."),
    (lambda n: n in (".", ".."), "Name must not be a path traversal segment."),
    (
        lambda n: any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in n),
        "Name must not contain control characters.",
    ),
    (lambda n: n.endswith((".", " ")), "Name must not end with a dot or space."),
    (_is_reserved, "Name is a reserved device name."),
)


def validate_name_segment(raw: str) -> str:
    """Validate and normalise a single path segment, or raise ``InvalidNameError``.

    Returns the surrounding-whitespace-stripped name to store.
    """
    name = raw.strip()
    for rejects, message in _NAME_RULES:
        if rejects(name):
            raise InvalidNameError(message)
    return name
