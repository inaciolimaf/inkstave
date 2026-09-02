"""Cross-file project map: parse + stitch \\input-resolved outline (spec 48)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from inkstave.agent.context.models import (
    FileEntry,
    ProjectMap,
    StructureKind,
    StructureNode,
)
from inkstave.agent.context.parser import parse_latex_structure

FileReader = Callable[[str], "str | None"]

# Content-hash → ProjectMap (memory cache; optional, must not change results).
_CACHE: dict[str, ProjectMap] = {}


def _candidates(target: str, including: str) -> list[str]:
    base = target.strip()
    variants = [base, f"{base}.tex"]
    if "/" in including:
        prefix = including.rsplit("/", 1)[0] + "/"
        variants += [f"{prefix}{base}", f"{prefix}{base}.tex"]
    return variants


@dataclass(slots=True)
class _Sources:
    """Every readable .tex file, already parsed, plus the detected main file."""

    contents: dict[str, str]
    parsed: dict[str, list[StructureNode]]
    main_file: str | None

    @property
    def digest(self) -> str:
        """Content hash over path + body, stable under dict ordering."""
        joined = "".join(f"{p}\0{self.contents[p]}\0" for p in sorted(self.contents))
        return hashlib.sha256(joined.encode()).hexdigest()

    def entries(self) -> list[FileEntry]:
        return [
            FileEntry(
                path=path,
                size=len(content),
                is_tex=path.endswith(".tex"),
                role="main" if path == self.main_file else "tex",
            )
            for path, content in self.contents.items()
        ]


def _read_sources(
    tex_paths: Sequence[str], file_reader: FileReader, extra_commands: Sequence[str]
) -> _Sources:
    """Read and parse every path the reader can supply; unreadable ones are skipped."""
    contents: dict[str, str] = {}
    parsed: dict[str, list[StructureNode]] = {}
    main_file: str | None = None
    for path in tex_paths:
        content = file_reader(path)
        if content is None:
            continue
        contents[path] = content
        if main_file is None and "\\documentclass" in content:
            main_file = path
        parsed[path] = parse_latex_structure(content, path, extra_commands)
    return _Sources(contents, parsed, main_file)


class _Stitcher:
    """Resolves \\input targets and splices the included outlines in place."""

    def __init__(self, parsed: dict[str, list[StructureNode]]) -> None:
        self._parsed = parsed
        self.unresolved: list[str] = []

    def _resolve(self, target: str, including: str) -> str | None:
        return next((c for c in _candidates(target, including) if c in self._parsed), None)

    def outline(self, path: str, visiting: frozenset[str] = frozenset()) -> list[StructureNode]:
        if path in visiting:
            return []  # include-cycle guard
        nodes = [n.model_copy(deep=True) for n in self._parsed.get(path, [])]
        self._walk(nodes, path, visiting)
        return nodes

    def _walk(self, items: list[StructureNode], path: str, visiting: frozenset[str]) -> None:
        for node in items:
            if node.kind == StructureKind.INPUT:
                self._splice(node, path, visiting)
            self._walk(node.children, path, visiting)

    def _splice(self, node: StructureNode, path: str, visiting: frozenset[str]) -> None:
        target = self._resolve(node.title or "", path)
        if target is None:
            self.unresolved.append(node.title or "")
            return
        node.target_path = target
        node.children = self.outline(target, visiting | {path})


def build_project_map(
    project_id: str,
    tex_paths: Sequence[str],
    file_reader: FileReader,
    *,
    extra_commands: Sequence[str] = (),
    cache: str = "memory",
) -> ProjectMap:
    sources = _read_sources(tex_paths, file_reader, extra_commands)
    digest = sources.digest
    cache_key = f"{project_id}:{digest}"
    if cache == "memory" and cache_key in _CACHE:
        return _CACHE[cache_key]

    stitcher = _Stitcher(sources.parsed)
    root = sources.main_file or next(iter(sources.parsed), None)
    outline = stitcher.outline(root) if root else []

    project_map = ProjectMap(
        project_id=project_id,
        main_file=sources.main_file,
        files=sources.entries(),
        outline=outline,
        # Dedupe unresolved inputs (the same missing target can be reached via
        # several include sites) while preserving first-seen order.
        unresolved_inputs=list(dict.fromkeys(stitcher.unresolved)),
        content_hash=digest,
    )
    if cache == "memory":
        _CACHE[cache_key] = project_map
    return project_map
