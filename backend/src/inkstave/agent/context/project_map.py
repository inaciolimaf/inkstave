"""Cross-file project map: parse + stitch \\input-resolved outline (spec 48)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence

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


def build_project_map(
    project_id: str,
    tex_paths: Sequence[str],
    file_reader: FileReader,
    *,
    extra_commands: Sequence[str] = (),
    cache: str = "memory",
) -> ProjectMap:
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

    digest = hashlib.sha256(
        "".join(f"{p}\0{contents[p]}\0" for p in sorted(contents)).encode()
    ).hexdigest()
    cache_key = f"{project_id}:{digest}"
    if cache == "memory" and cache_key in _CACHE:
        return _CACHE[cache_key]

    files = [
        FileEntry(
            path=p,
            size=len(c),
            is_tex=p.endswith(".tex"),
            role="main" if p == main_file else "tex",
        )
        for p, c in contents.items()
    ]

    unresolved: list[str] = []

    def resolve(target: str, including: str) -> str | None:
        for cand in _candidates(target, including):
            if cand in parsed:
                return cand
        return None

    def stitch(path: str, visiting: frozenset[str]) -> list[StructureNode]:
        if path in visiting:
            return []  # include-cycle guard
        nodes = [n.model_copy(deep=True) for n in parsed.get(path, [])]

        def walk(items: list[StructureNode]) -> None:
            for node in items:
                if node.kind == StructureKind.INPUT:
                    target = resolve(node.title or "", path)
                    if target is not None:
                        node.target_path = target
                        node.children = stitch(target, visiting | {path})
                    else:
                        unresolved.append(node.title or "")
                walk(node.children)

        walk(nodes)
        return nodes

    root = main_file or (next(iter(parsed), None))
    outline = stitch(root, frozenset()) if root else []

    # Dedupe unresolved inputs (the same missing target can be reached via several
    # include sites) while preserving first-seen order.
    unique_unresolved = list(dict.fromkeys(unresolved))

    project_map = ProjectMap(
        project_id=project_id,
        main_file=main_file,
        files=files,
        outline=outline,
        unresolved_inputs=unique_unresolved,
        content_hash=digest,
    )
    if cache == "memory":
        _CACHE[cache_key] = project_map
    return project_map
