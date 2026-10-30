"""Serializable structure/context models (spec 48). No DB tables."""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field

# Sectioning depth: lower nests outer. Matches LaTeX's standard hierarchy.
SECTION_LEVELS: dict[str, int] = {
    "part": -1,
    "chapter": 0,
    "section": 1,
    "subsection": 2,
    "subsubsection": 3,
    "paragraph": 4,
    "subparagraph": 5,
}

# Environments whose contents must NOT be parsed for commands (opaque).
VERBATIM_ENVS: frozenset[str] = frozenset(
    {"verbatim", "Verbatim", "lstlisting", "minted", "comment", "verbatim*", "lstlisting*"}
)

# Environments worth surfacing as structure nodes.
NOTABLE_ENVS: frozenset[str] = frozenset(
    {
        "figure",
        "figure*",
        "table",
        "table*",
        "equation",
        "equation*",
        "align",
        "align*",
        "itemize",
        "enumerate",
        "abstract",
        "verbatim",
        "lstlisting",
        "minted",
    }
)


class StructureKind(enum.StrEnum):
    PREAMBLE = "preamble"
    SECTIONING = "sectioning"
    ENVIRONMENT = "environment"
    INPUT = "input"


class StructureNode(BaseModel):
    kind: StructureKind
    command: str | None = None  # section name or environment name
    level: int | None = None
    title: str | None = None
    label: str | None = None
    file_path: str
    start_line: int  # 1-based inclusive
    end_line: int  # inclusive
    start_char: int  # 0-based offset into the file content
    end_char: int
    target_path: str | None = None  # for INPUT: resolved referenced path
    children: list[StructureNode] = Field(default_factory=list)


class FileEntry(BaseModel):
    path: str
    size: int
    is_tex: bool
    role: str  # "main" | "tex" | "asset"


class ProjectMap(BaseModel):
    project_id: str
    main_file: str | None = None
    files: list[FileEntry] = Field(default_factory=list)
    outline: list[StructureNode] = Field(default_factory=list)
    unresolved_inputs: list[str] = Field(default_factory=list)
    content_hash: str = ""


class SectionMatch(BaseModel):
    node: StructureNode
    score: float
    reason: str


class ContextChunk(BaseModel):
    kind: str  # "outline" | "section" | "surrounding" | "search"
    file_path: str | None = None
    title: str | None = None
    text: str
    priority: int  # lower = kept first
    truncated: bool = False


class ContextBundle(BaseModel):
    goal: str
    chunks: list[ContextChunk] = Field(default_factory=list)
    estimated_tokens: int = 0
    budget_tokens: int = 0
