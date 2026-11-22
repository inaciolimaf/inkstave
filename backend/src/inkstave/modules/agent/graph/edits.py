"""Staged edit intents (spec 42), as exact-text replacements.

A ``StagedEdit`` says "replace ``old_text`` with ``new_text``" in one document. The model
never gives line numbers: ``old_text`` must occur exactly once in the document's current
text, so an edit that no longer matches the file is refused rather than applied in the
wrong place. ``propose_edit`` checks this when it stages the edit; ``materialize_diffs``
checks it again at the end of the turn, against the content it reads then.

Edits to one document apply in the order they were staged, each to the text the previous
one produced. The pure helpers here hold that rule.
"""

from __future__ import annotations

import enum
from uuid import UUID

from pydantic import BaseModel, Field


class DiffConflictError(Exception):
    """A staged edit cannot be applied to the document's current text."""


class StagedEdit(BaseModel):
    edit_id: str
    doc_id: str
    path: str
    base_version: str  # the doc version the model read before staging the edit
    old_text: str  # occurs once in the text it applies to; "" only for an empty file
    new_text: str
    rationale: str | None = Field(default=None)


def apply_edit(text: str, edit: StagedEdit) -> str:
    """``text`` with ``edit`` applied, or ``DiffConflictError`` when it does not fit exactly once."""
    if edit.old_text == "":
        if text == "":
            return edit.new_text
        raise DiffConflictError("an empty old_text only applies to an empty file")
    found = text.count(edit.old_text)
    if found != 1:
        raise DiffConflictError(f"old_text occurs {found} times in the current file; it must occur once")
    return text.replace(edit.old_text, edit.new_text, 1)


def apply_edits(text: str, edits: list[StagedEdit]) -> str:
    """Apply ``edits`` in order, each to the text the previous one produced."""
    for edit in edits:
        text = apply_edit(text, edit)
    return text


class FileOpKind(enum.StrEnum):
    create = "create"
    delete = "delete"
    move = "move"


class StagedFileOp(BaseModel):
    """A change to the tree the agent proposes; stored at the end of the turn, never applied."""

    kind: FileOpKind
    entity_type: str  # the tree entity's type: "doc", "folder" or "file"
    path: str  # where the entity is, or for a create where it will be
    entity_id: UUID | None = None  # the target of a delete or move
    new_path: str | None = None  # a move's destination
    content: str | None = None  # a new document's text
    affected_paths: list[str] = Field(default_factory=list)  # what a delete removes
    rationale: str | None = None
