"""Pure path helpers shared by the proposal tools and the apply step."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def normalize_path(raw: str) -> str:
    """A project-relative path as the tree spells it, whatever the model wrote around it."""
    path = raw.strip()
    while path.startswith("./"):
        path = path[2:]
    return path.strip("/")


def parent_of(path: str) -> str:
    """The folder part of ``path``; empty for the project root."""
    return path.rpartition("/")[0]


def name_of(path: str) -> str:
    return path.rpartition("/")[2]


def ancestors_of(path: str) -> list[str]:
    """Every folder above ``path``, outermost first."""
    segments = path.split("/")[:-1]
    return ["/".join(segments[: i + 1]) for i in range(len(segments))]


def subtree_paths(all_paths: Iterable[str], root: str) -> list[str]:
    """``root`` and everything under it, sorted: what deleting ``root`` removes."""
    return sorted(p for p in all_paths if p == root or p.startswith(f"{root}/"))
