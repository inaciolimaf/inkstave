"""Context-window selection within a token budget (spec 48). Deterministic."""

from __future__ import annotations

from collections.abc import Callable

from inkstave.agent.context.locate import locate_section
from inkstave.agent.context.models import (
    ContextBundle,
    ContextChunk,
    ProjectMap,
    StructureKind,
    StructureNode,
)

FileReader = Callable[[str], "str | None"]
TokenCounter = Callable[[str], int]

_TRUNCATION_MARKER = "\n… [truncated]"


def estimate_tokens(text: str) -> int:
    """A deterministic token estimate (~4 chars/token). Swappable via DI."""
    return max(1, (len(text) + 3) // 4)


def _outline_summary(project_map: ProjectMap) -> str:
    lines = [f"Project map ({len(project_map.files)} files, main: {project_map.main_file}):"]

    def walk(nodes: list[StructureNode], depth: int) -> None:
        for node in nodes:
            if node.kind == StructureKind.SECTIONING:
                indent = "  " * depth
                lines.append(f"{indent}- {node.command}: {node.title or ''} [{node.file_path}]")
                walk(node.children, depth + 1)
            else:
                walk(node.children, depth)

    walk(project_map.outline, 0)
    return "\n".join(lines)


def _section_text(content: str, node: StructureNode, surrounding: int) -> str:
    lines = content.split("\n")
    start = max(0, node.start_line - 1 - surrounding)
    end = min(len(lines), node.end_line + surrounding)
    return "\n".join(lines[start:end])


def _fit(chunk: ContextChunk, remaining: int, count: TokenCounter) -> ContextChunk | None:
    """Return the chunk if it fits; else a deterministically truncated copy, or None."""
    if count(chunk.text) <= remaining:
        return chunk
    lines = chunk.text.split("\n")
    kept: list[str] = []
    for line in lines:
        trial = "\n".join([*kept, line]) + _TRUNCATION_MARKER
        if count(trial) > remaining:
            break
        kept.append(line)
    if not kept:
        return None
    return chunk.model_copy(
        update={"text": "\n".join(kept) + _TRUNCATION_MARKER, "truncated": True}
    )


def select_context(
    project_map: ProjectMap,
    file_reader: FileReader,
    goal: str,
    budget_tokens: int,
    *,
    surrounding_lines: int = 40,
    token_count: TokenCounter = estimate_tokens,
) -> ContextBundle:
    candidates: list[ContextChunk] = []

    # Priority 0: the target section's content + surrounding lines.
    matches = locate_section(project_map, goal)
    target = matches[0].node if matches else None
    if target is not None:
        content = file_reader(target.file_path)
        if content is not None:
            candidates.append(
                ContextChunk(
                    kind="section",
                    file_path=target.file_path,
                    title=target.title,
                    text=_section_text(content, target, surrounding_lines),
                    priority=0,
                )
            )

    # Priority 1: a compact outline summary.
    candidates.append(ContextChunk(kind="outline", text=_outline_summary(project_map), priority=1))

    # Priority 2: the next-highest-ranked sibling matches' titles (cheap grounding).
    for match in matches[1:4]:
        candidates.append(
            ContextChunk(
                kind="search",
                file_path=match.node.file_path,
                title=match.node.title,
                text=f"Related: {match.node.command} '{match.node.title}' "
                f"({match.node.file_path}:{match.node.start_line})",
                priority=2,
            )
        )

    candidates.sort(key=lambda c: c.priority)
    chosen: list[ContextChunk] = []
    used = 0
    for chunk in candidates:
        fitted = _fit(chunk, budget_tokens - used, token_count)
        if fitted is None:
            continue  # drop lowest-priority chunks that don't fit
        chosen.append(fitted)
        used += token_count(fitted.text)

    return ContextBundle(
        goal=goal, chunks=chosen, estimated_tokens=used, budget_tokens=budget_tokens
    )
