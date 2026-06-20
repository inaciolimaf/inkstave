"""Agent egress lock (spec 105 §5.7).

The AI agent's tools (search_project, read_file, list_tree, locate_section,
propose_edit) must NEVER reach the network — only the LLM/OpenRouter client may
make outbound calls. This is a regression guard: it statically scans the
`agent/tools/` package and fails if any tool module imports a network client, so
a future PR that adds a URL-fetching tool trips this test instead of silently
opening an egress path from inside a sandboxed deployment.
"""

from __future__ import annotations

import ast
from pathlib import Path

import inkstave.agent.tools as tools_pkg
from inkstave.agent.tools import default_registry

# Outbound-network clients no agent tool may import.
_FORBIDDEN_TOP_LEVEL = {
    "socket",
    "ssl",
    "http",  # http.client
    "urllib",  # urllib.request
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "websockets",
    "httpcore",
}


def _tool_module_files() -> list[Path]:
    pkg_dir = Path(tools_pkg.__file__).parent
    return sorted(p for p in pkg_dir.glob("*.py") if p.name != "__pycache__")


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_registry_contains_only_the_five_known_tools() -> None:
    # If a new tool appears, this test (and the scan below) must be revisited.
    names = {spec.name for spec in default_registry().specs()}
    assert names == {
        "search_project",
        "read_file",
        "list_tree",
        "locate_section",
        "propose_edit",
    }


def test_no_agent_tool_module_imports_a_network_client() -> None:
    offenders: dict[str, set[str]] = {}
    for path in _tool_module_files():
        imported = _imported_modules(path.read_text("utf-8"))
        bad = imported & _FORBIDDEN_TOP_LEVEL
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"agent tools must not import network clients: {offenders}"
