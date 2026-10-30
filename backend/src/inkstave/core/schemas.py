"""Shared request-model base enforcing strict validation (spec 52 §5.2.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Request bodies extend this so unknown fields are rejected (422).

    ``extra="forbid"`` blocks request smuggling of unexpected keys; ``str_strip_whitespace``
    normalizes input. Per-field ``max_length`` bounds remain the field's responsibility.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
