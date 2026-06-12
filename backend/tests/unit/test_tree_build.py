"""Unit tests for in-memory tree assembly (build_tree, compute_path)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.services.tree_service import build_tree, compute_path

_DT = datetime(2026, 1, 1, tzinfo=UTC)
_PID = uuid4()


def _entity(
    name: str,
    type_: TreeEntityType,
    parent_id: UUID | None,
    *,
    is_root: bool = False,
) -> TreeEntity:
    return TreeEntity(
        id=uuid4(),
        project_id=_PID,
        parent_id=parent_id,
        type=type_,
        name=name,
        is_root=is_root,
        created_at=_DT,
        updated_at=_DT,
    )


def test_build_tree_orders_folders_first_then_by_name() -> None:
    root = _entity("", TreeEntityType.folder, None, is_root=True)
    b = _entity("B", TreeEntityType.folder, root.id)
    a = _entity("A", TreeEntityType.folder, root.id)
    doc_c = _entity("c.tex", TreeEntityType.doc, root.id)
    doc_a = _entity("a.tex", TreeEntityType.doc, root.id)

    tree = build_tree([root, b, a, doc_c, doc_a])
    assert tree.root.is_root is True
    assert tree.root.children is not None
    names = [child.name for child in tree.root.children]
    assert names == ["A", "B", "a.tex", "c.tex"]
    # Docs carry no children list.
    assert tree.root.children[2].children is None


def test_compute_path_is_derived_from_ancestors() -> None:
    root = _entity("", TreeEntityType.folder, None, is_root=True)
    figures = _entity("figures", TreeEntityType.folder, root.id)
    diagram = _entity("diagram.tex", TreeEntityType.doc, figures.id)
    by_id = {root.id: root, figures.id: figures, diagram.id: diagram}

    assert compute_path(root, by_id) == ""
    assert compute_path(figures, by_id) == "figures"
    assert compute_path(diagram, by_id) == "figures/diagram.tex"
