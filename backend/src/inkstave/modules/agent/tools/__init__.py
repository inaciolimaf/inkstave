"""Agent tools + registry assembly (spec 42)."""

from inkstave.modules.agent.tools.base import (
    Tool,
    ToolContext,
    ToolError,
    ToolRegistry,
    ToolResult,
    authorize,
)
from inkstave.modules.agent.tools.list_tree import ListTreeTool
from inkstave.modules.agent.tools.locate_section import LocateSectionTool
from inkstave.modules.agent.tools.propose_edit import ProposeEditTool
from inkstave.modules.agent.tools.files.propose import (
    ProposeCreateTool,
    ProposeDeleteTool,
    ProposeMoveTool,
)
from inkstave.modules.agent.tools.read_file import ReadFileTool
from inkstave.modules.agent.tools.search_project import SearchProjectTool
from inkstave.modules.agent.tools.files.view_image import ViewImageTool


def default_registry() -> ToolRegistry:
    """The built-in tools, bound into a registry for ``AgentDeps``."""
    registry = ToolRegistry()
    for tool in (
        SearchProjectTool(),
        ReadFileTool(),
        ListTreeTool(),
        LocateSectionTool(),
        ProposeEditTool(),
        ViewImageTool(),
        ProposeCreateTool(),
        ProposeDeleteTool(),
        ProposeMoveTool(),
    ):
        registry.register(tool)
    return registry


__all__ = [
    "ListTreeTool",
    "LocateSectionTool",
    "ProposeCreateTool",
    "ProposeDeleteTool",
    "ProposeEditTool",
    "ProposeMoveTool",
    "ReadFileTool",
    "SearchProjectTool",
    "Tool",
    "ToolContext",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "ViewImageTool",
    "authorize",
    "default_registry",
]
