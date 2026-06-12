"""Path-segment validation for tree-entity names (spec 12).

Reimplements the *rules* of Overleaf's SafePath independently: a name is a single
path segment, free of traversal/separators/control characters and
Windows-hostile forms. Reused by specs 13/14. Names are stored as given (after a
surrounding-whitespace strip); uniqueness is enforced case-insensitively at the
DB layer.
"""

from __future__ import annotations

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


def validate_name_segment(raw: str) -> str:
    """Validate and normalise a single path segment, or raise ``InvalidNameError``.

    Returns the surrounding-whitespace-stripped name to store.
    """
    name = raw.strip()
    if not name:
        raise InvalidNameError("Name must not be empty.")
    if len(name) > MAX_TREE_ENTITY_NAME_LENGTH:
        raise InvalidNameError("Name is too long.")
    if "/" in name or "\\" in name:
        raise InvalidNameError("Name must not contain a path separator.")
    if name in (".", ".."):
        raise InvalidNameError("Name must not be a path traversal segment.")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
        raise InvalidNameError("Name must not contain control characters.")
    if name.endswith((".", " ")):
        raise InvalidNameError("Name must not end with a dot or space.")
    stem = name.split(".", 1)[0]
    if name.lower() in _RESERVED_NAMES or stem.lower() in _RESERVED_NAMES:
        raise InvalidNameError("Name is a reserved device name.")
    return name
