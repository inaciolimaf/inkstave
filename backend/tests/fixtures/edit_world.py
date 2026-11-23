"""An in-memory project for the edit-path tool tests (spec 42): a tree and its document texts.

The shared tree helpers (`get_tree`, `get_document`) and the access check of the tools are
replaced. Resolution, paths, windows, caps and the exact-match rules run for real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from inkstave.modules.agent.tools import _common, propose_edit, read_file
from inkstave.modules.agent.tools.base import ToolContext, ToolError
from inkstave.modules.projects import EntityNotFoundError, NotADocumentError
from inkstave.modules.projects.models.tree_entity import TreeEntityType

MAIN_TEXT = "\\section{A}\nalpha\n\\section{B}\nbeta\n"  # 4 lines
THREE_LINES = "one\ntwo\nthree\n"


@dataclass
class Entity:
    id: UUID
    type: TreeEntityType
    name: str
    parent_id: UUID | None = None
    is_root: bool = False


@dataclass
class Doc:
    content: str
    version: int


@dataclass
class EditWorld:
    """Entities of one project, the text of each document, and the access check's answer."""

    monkeypatch: pytest.MonkeyPatch
    project_id: UUID = field(default_factory=uuid4)
    denied: ToolError | None = None
    auth_calls: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = uuid4()
        self.main, self.dup, self.empty = uuid4(), uuid4(), uuid4()
        self.folder, self.nested = uuid4(), uuid4()
        self.entities: dict[UUID, Entity] = {
            self.root: Entity(self.root, TreeEntityType.folder, "", is_root=True),
            self.main: Entity(self.main, TreeEntityType.doc, "main.tex", self.root),
            self.dup: Entity(self.dup, TreeEntityType.doc, "dup.tex", self.root),
            self.empty: Entity(self.empty, TreeEntityType.doc, "empty.tex", self.root),
            self.folder: Entity(self.folder, TreeEntityType.folder, "x", self.root),
            self.nested: Entity(self.nested, TreeEntityType.doc, "y.tex", self.folder),
        }
        self.docs: dict[UUID, Doc] = {
            self.main: Doc(MAIN_TEXT, 3),
            self.dup: Doc("x\nx\n", 1),
            self.empty: Doc("", 0),
            self.nested: Doc(THREE_LINES, 0),
        }
        self.monkeypatch.setattr(_common, "get_tree", self._get_tree)
        self.monkeypatch.setattr(_common, "get_document", self._get_document)
        self.monkeypatch.setattr(read_file, "authorize", self._authorize)
        self.monkeypatch.setattr(propose_edit, "authorize", self._authorize)

    async def _get_tree(self, _db: object, _project_id: UUID) -> list[Entity]:
        return list(self.entities.values())

    async def _get_document(self, _db: object, _project_id: UUID, entity_id: UUID) -> Doc:
        if entity_id not in self.entities:
            raise EntityNotFoundError()
        if self.entities[entity_id].type != TreeEntityType.doc:
            raise NotADocumentError()
        return self.docs[entity_id]

    async def _authorize(self, ctx: ToolContext, **kwargs: Any) -> ToolError | None:
        self.auth_calls.append({"ctx": ctx, **kwargs})
        return self.denied

    def ctx(self, *, read_max: int = 40000, edit_max: int = 200000) -> ToolContext:
        settings = SimpleNamespace(agent_tool_read_max_chars=read_max, agent_tool_edit_max_chars=edit_max)
        return ToolContext(
            db=None,  # type: ignore[arg-type]  # the fakes never touch the session
            project_id=str(self.project_id),
            user_id=str(uuid4()),
            settings=settings,  # type: ignore[arg-type]  # only the two limits are read
        )
