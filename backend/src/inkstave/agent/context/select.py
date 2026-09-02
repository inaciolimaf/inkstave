"""Context-window selection within a token budget (spec 48). Deterministic."""

from __future__ import annotations

from collections.abc import Callable

from inkstave.agent.context.locate import locate_section
from inkstave.agent.context.models import (
    ContextBundle,
    ContextChunk,
    ProjectMap,
    SectionMatch,
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


def _target_chunk(
    match_node: StructureNode, file_reader: FileReader, surrounding_lines: int
) -> ContextChunk | None:
    """Priority 0: the target section's content + surrounding lines."""
    content = file_reader(match_node.file_path)
    if content is None:
        return None
    return ContextChunk(
        kind="section",
        file_path=match_node.file_path,
        title=match_node.title,
        text=_section_text(content, match_node, surrounding_lines),
        priority=0,
    )


def _related_chunk(match: SectionMatch) -> ContextChunk:
    """Priority 2: a sibling match's title (cheap grounding)."""
    node = match.node
    return ContextChunk(
        kind="search",
        file_path=node.file_path,
        title=node.title,
        text=f"Related: {node.command} '{node.title}' ({node.file_path}:{node.start_line})",
        priority=2,
    )


def _candidates(
    project_map: ProjectMap,
    file_reader: FileReader,
    matches: list[SectionMatch],
    surrounding_lines: int,
) -> list[ContextChunk]:
    """Every chunk worth considering, in no particular order."""
    chunks: list[ContextChunk] = []
    if matches:
        target = _target_chunk(matches[0].node, file_reader, surrounding_lines)
        if target is not None:
            chunks.append(target)
    # Priority 1: a compact outline summary.
    chunks.append(ContextChunk(kind="outline", text=_outline_summary(project_map), priority=1))
    chunks.extend(_related_chunk(m) for m in matches[1:4])
    return chunks


def select_context(
    project_map: ProjectMap,
    file_reader: FileReader,
    goal: str,
    budget_tokens: int,
    *,
    surrounding_lines: int = 40,
    token_count: TokenCounter = estimate_tokens,
) -> ContextBundle:
    matches = locate_section(project_map, goal)
    candidates = _candidates(project_map, file_reader, matches, surrounding_lines)
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
