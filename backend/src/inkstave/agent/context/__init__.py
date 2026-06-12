"""LaTeX structure parsing, project map, and context selection for the agent (spec 48)."""

from inkstave.agent.context.locate import locate_section
from inkstave.agent.context.models import (
    ContextBundle,
    ContextChunk,
    FileEntry,
    ProjectMap,
    SectionMatch,
    StructureKind,
    StructureNode,
)
from inkstave.agent.context.parser import parse_latex_structure
from inkstave.agent.context.project_map import build_project_map
from inkstave.agent.context.select import estimate_tokens, select_context

__all__ = [
    "ContextBundle",
    "ContextChunk",
    "FileEntry",
    "ProjectMap",
    "SectionMatch",
    "StructureKind",
    "StructureNode",
    "build_project_map",
    "estimate_tokens",
    "locate_section",
    "parse_latex_structure",
    "select_context",
]
