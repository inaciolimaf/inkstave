from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProposedFileOpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_id: UUID | None  # the turn's last message; the transcript places the proposal after it
    kind: Literal["create", "delete", "move"]
    entity_type: str
    path: str
    new_path: str | None
    content: str | None
    affected_paths: list[str]
    status: Literal["proposed", "applied", "rejected", "superseded"]
    rationale: str | None
    created_at: datetime
