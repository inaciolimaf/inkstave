"""Agent tools + registry assembly (spec 42)."""

from inkstave.agent.tools.base import (
    Tool,
    ToolContext,
    ToolError,
    ToolRegistry,
    ToolResult,
    authorize,
)
from inkstave.agent.tools.list_tree import ListTreeTool
from inkstave.agent.tools.locate_section import LocateSectionTool
from inkstave.agent.tools.propose_edit import ProposeEditTool
from inkstave.agent.tools.read_file import ReadFileTool
from inkstave.agent.tools.search_project import SearchProjectTool


def default_registry() -> ToolRegistry:
    """The five built-in tools, bound into a registry for ``AgentDeps``."""
    registry = ToolRegistry()
    for tool in (
        SearchProjectTool(),
        ReadFileTool(),
        ListTreeTool(),
        LocateSectionTool(),
        ProposeEditTool(),
    ):
        registry.register(tool)
    return registry


__all__ = [
    "ListTreeTool",
    "LocateSectionTool",
    "ProposeEditTool",
    "ReadFileTool",
    "SearchProjectTool",
    "Tool",
    "ToolContext",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "authorize",
    "default_registry",
]
