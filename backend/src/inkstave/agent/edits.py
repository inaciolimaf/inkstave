"""Staged edit intents (spec 42).

A ``StagedEdit`` is the *input* to spec 43's diff computation — it deliberately holds
no diff. ``propose_edit`` appends these to ``AgentState.staged_edits``; spec 43 groups
them by ``doc_id`` and computes per-file unified diffs against current content.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class EditMode(enum.StrEnum):
    full = "full"  # replace the whole document
    range = "range"  # replace [start_line, end_line)


class StagedEdit(BaseModel):
    edit_id: str
    doc_id: str
    path: str
    base_version: str  # the doc version this edit was authored against (drift check, spec 43)
    mode: EditMode
    new_text: str
    start_line: int | None = None  # required for mode="range", 0-based inclusive
    end_line: int | None = None  # required for mode="range", 0-based exclusive
    rationale: str | None = Field(default=None)
