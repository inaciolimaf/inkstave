# Spec 48 — Agent Context & LaTeX Section Parsing (requirements)

## 1. Summary

This spec gives the agent precise awareness of a LaTeX project. It adds three
things, all server-side: (1) a **LaTeX structure parser** that scans `.tex`
content and maps sectioning commands and key environments to **file + line/char
ranges**; (2) a **project map / context builder** that aggregates these
structures across the project's files (following `\input`/`\include`) into a
compact, grounded representation the agent's tools use; and (3)
**context-window management** that selects the most relevant chunks to send to
the LLM within a token budget. It directly sharpens spec-42's `locate_section`
tool so "edit the introduction" resolves to the right file and range. We write
our own lightweight parser; we do **not** copy Overleaf's lezer-latex grammar and
do not build a full LaTeX AST/compiler.

## 2. Context & dependencies

- **Depends on:**
  - spec **42** — agent tools. Provides `search_project`, `read_file`,
    `locate_section`, `propose_edit`. This spec replaces `locate_section`'s
    naive matching with a structure-aware resolver and provides the project map
    those tools consume.
  - spec **18** — editor/document model. Provides access to document content per
    file (the parser reads the current text of each `.tex` document).
  - specs **41–44** (agent core/streaming) assumed present; tools run inside the
    LangGraph graph with the DI-provided LLM client (FakeLLM in tests).
- **Unlocks:** spec **49** (safety/evals will assert section-location accuracy
  and context-budget behaviour against this); better diffs from spec 43 because
  the agent edits the right ranges.
- **Affected areas:** backend (`backend/` agent package), docs. No frontend, no
  new DB tables (parsing is computed on demand and cached in memory/Redis).

## 3. Goals

- A pure-function **`parse_latex_structure(text) -> StructureNode tree`** that
  identifies, with line and character offsets:
  - sectioning commands: `\part`, `\chapter`, `\section`, `\subsection`,
    `\subsubsection`, `\paragraph`, `\subparagraph` (starred variants too), with
    nesting by level;
  - the document body (`\begin{document}`…`\end{document}`) and preamble split;
  - labelled/important environments (e.g. `figure`, `table`, `equation`,
    `align`, `itemize`, `enumerate`, `abstract`, `verbatim`/`lstlisting` — and
    treat verbatim-like environments as opaque so their contents are not
    misparsed);
  - `\input{...}` / `\include{...}` / `\subfile{...}` references (so the map can
    follow them).
- A **`build_project_map(project)`** that walks the project's file tree, parses
  each `.tex` file, resolves `\input`/`\include` into a cross-file outline, and
  produces a serializable **project map** (outline of sections → file + range,
  plus a file list with sizes/roles such as "main document" = the file with
  `\documentclass`).
- A structure-aware **`locate_section(query)`** resolver: given a natural query
  ("the introduction", "section 2", "the methods section", "the abstract"),
  return the best-matching node(s) with `file_path`, `start_line`, `end_line`,
  `char_range`, and a confidence/score — improving spec 42's tool.
- **Context-window management**: a `select_context(query/goal, budget_tokens)`
  that picks the most relevant chunks (target section + surrounding context +
  project map summary) to fit a configurable token budget, with deterministic,
  testable selection and truncation.
- Robustness: the parser never throws on malformed LaTeX; it degrades to
  best-effort and is fast (linear scan) so it stays inside the test budget.

## 4. Non-goals (explicitly out of scope)

- A full LaTeX AST / macro-expanding parser or a TeX compiler. This is a
  *structural* scan, not semantic LaTeX evaluation.
- Resolving custom user-defined sectioning macros via macro expansion (recognize
  the standard commands; custom macros are out of scope beyond a configurable
  extra-commands list).
- The chat UI (46), diff review/apply (47), safety/rate-limits/evals (49).
- Persisting the parse to the database; results are computed on demand and may be
  cached in memory/Redis keyed by content hash (cache is an optimization, not a
  schema).
- Embeddings / vector search. Selection is structural + lexical, deterministic,
  and mockable (no external embedding service in this spec).

## 5. Detailed requirements

### 5.1 Data model

In-memory / serializable types (Pydantic v2 models in the agent package). No DB
tables, no migration.

```py
class StructureKind(str, Enum):
    PREAMBLE = "preamble"
    SECTIONING = "sectioning"   # part..subparagraph
    ENVIRONMENT = "environment" # figure, table, equation, ...
    INPUT = "input"             # \input / \include / \subfile

class StructureNode(BaseModel):
    kind: StructureKind
    command: str | None          # e.g. "section", "subsection", or env name
    level: int | None            # sectioning depth: part=-1..subparagraph=5
    title: str | None            # section title / env label if any
    label: str | None            # \label{...} captured within the node, if present
    file_path: str
    start_line: int              # 1-based, inclusive
    end_line: int                # inclusive; spans to next sibling/parent boundary
    start_char: int              # 0-based offset into the file content
    end_char: int
    target_path: str | None      # for INPUT: resolved referenced file path
    children: list["StructureNode"]

class ProjectMap(BaseModel):
    project_id: str
    main_file: str | None        # file containing \documentclass
    files: list[FileEntry]       # path, size, is_tex, role
    outline: list[StructureNode] # cross-file section tree (input-resolved)
    content_hash: str            # of all parsed inputs, for caching
```

`end_line`/`end_char` of a sectioning node extend to just before the next
sibling-or-higher sectioning command (or end of body), giving each section a
contiguous editable range.

### 5.2 Backend / module contracts

New module, e.g. `backend/app/agent/context/`:

- `parse_latex_structure(text: str, file_path: str) -> list[StructureNode]`
  - Pure, deterministic, no I/O. Single linear scan (regex/state-machine over
    lines, tracking brace/verbatim/comment state). Returns top-level nodes with
    nested children. Strips `%` comments from command detection (respecting
    `\%`), and treats verbatim-like environments as opaque.
  - Captures starred variants (`\section*`) and an immediately-following
    `\label{...}`.
- `build_project_map(project_id, file_reader) -> ProjectMap`
  - `file_reader` is an injected callable `(path) -> str | None` (so tests inject
    fixtures; production reads document content from spec 13/18 storage). Walks
    `.tex` files, parses each, resolves `\input`/`\include`/`\subfile` paths
    (with/without `.tex`, relative to the project root and to the including
    file), and stitches an `outline`. Detects `main_file` by `\documentclass`.
    Guards against include cycles and missing targets (record as unresolved).
  - Caches by `content_hash` (in-memory LRU and/or Redis); cache is optional and
    must not change results.
- `locate_section(project_map, query: str) -> list[SectionMatch]`
  - Resolves a natural query to nodes. Matching strategy (deterministic, no LLM):
    normalize case/whitespace; match against section titles, common synonyms
    ("intro"→introduction, "methods"/"methodology", "related work", "conclusion",
    "abstract", "references"/"bibliography"), ordinal/positional queries
    ("section 2", "the first subsection"), and `\label` names. Return ranked
    `SectionMatch{ node, score, reason }`. Empty list when nothing plausibly
    matches (caller decides what to do).
- `select_context(project_map, file_reader, goal: str, budget_tokens: int) -> ContextBundle`
  - Produces a `ContextBundle` containing: a compact project-map/outline summary;
    the target node's content (from `locate_section` on `goal`, if any) plus a
    configurable number of surrounding lines; and, if budget remains, adjacent
    sections or `search_project` hits. Uses a pluggable token-count function
    (injected; default a simple, deterministic estimator so tests are stable —
    real tokenizer can be swapped via DI). Truncates deterministically (drop
    lowest-priority chunks first; never split a hunk mid-line without a clear
    truncation marker). Returns the chunks plus the total estimated token count
    so callers can assert it is ≤ budget.

Integration with spec 42:
- Spec 42's `locate_section` tool delegates to this module's `locate_section`
  (and may include nearby content via `select_context`). Spec 42's `read_file`
  and `search_project` may consume the project map for grounding (e.g. resolving
  "the intro file"). The tool's external signature/result contract from spec 42
  is preserved; only its accuracy improves.

### 5.3 Frontend / UI

None. This is backend agent-context plumbing. (The improved section location and
context surface through the agent's chat/tool output in spec 46, but this spec
adds no UI.)

### 5.4 Real-time / jobs / external integrations

- No new ARQ jobs or WS messages. Parsing runs synchronously inside tool calls
  during an agent run (already orchestrated by spec 44). It must be fast enough
  not to dominate a run; cache by content hash.
- The token-count function is injected via DI; in tests it is a deterministic
  stub (no tiktoken/network dependency required for the fast suite).

### 5.5 Configuration

New env vars (add to `.env.example`, with sane defaults):

- `AGENT_CONTEXT_TOKEN_BUDGET` — default token budget for `select_context`
  (default e.g. `8000`).
- `AGENT_CONTEXT_SURROUNDING_LINES` — lines of context around a located section
  (default e.g. `40`).
- `AGENT_SECTION_EXTRA_COMMANDS` — optional comma-separated extra sectioning
  command names to recognize (default empty).
- `AGENT_CONTEXT_CACHE` — `memory` | `redis` | `off` (default `memory`).

## 6. Overleaf reference (study only — never copy)

- `services/web/frontend/js/features/source-editor/lezer-latex/` (`latex.grammar`,
  `tokens.mjs`, `README.md`) — read **only** to understand *conceptually* how
  LaTeX is tokenized/structured (commands, groups, environments, verbatim
  handling). **Do NOT copy or translate the grammar.** LaTeX's command/structure
  syntax is public knowledge; implement an independent, lightweight structural
  scanner suited to our needs (file+range mapping), not a full parser.
- **The agent and its context-building have NO Overleaf equivalent** — Overleaf
  has no AI agent, project-map-for-LLM, or context-window management. Build those
  entirely from this spec.

## 7. Acceptance criteria

1. **Given** a `.tex` string with nested sectioning, **when**
   `parse_latex_structure` runs, **then** it returns a tree with correct
   `command`/`level`/`title` and accurate 1-based `start_line`/`end_line` and
   `char_range` for each node, where each section's range extends to just before
   the next sibling-or-higher sectioning command.
2. **Given** starred sections (`\section*`), comments (`% \section{fake}`), and a
   `verbatim`/`lstlisting` block containing `\section{...}`, **when** parsed,
   **then** the commented and verbatim "sections" are **not** treated as
   sections, and starred sections are captured.
3. **Given** a multi-file project with `\input`/`\include`, **when**
   `build_project_map` runs (with a fixture `file_reader`), **then** the outline
   is stitched across files, each node carries its true `file_path`, `main_file`
   is the file with `\documentclass`, include cycles do not hang, and missing
   targets are recorded as unresolved.
4. **Given** the project map, **when** `locate_section("the introduction")`,
   `locate_section("section 2")`, and `locate_section("the abstract")` run,
   **then** each returns the correct node as the top-ranked match with a
   `file_path` + line range, and a clearly-unmatched query returns an empty list.
5. **Given** a goal and a `budget_tokens`, **when** `select_context` runs,
   **then** the returned bundle's estimated token count is ≤ the budget, includes
   the target section content plus configured surrounding lines and a project-map
   summary, and truncation is deterministic (lowest-priority chunks dropped
   first, with a truncation marker).
6. **Given** spec-42's `locate_section` tool is invoked during an agent run
   (FakeLLM), **when** it resolves a section query, **then** it uses this
   module and returns the structure-aware range (improved over the spec-42
   baseline), with the spec-42 tool contract unchanged.
7. **Given** malformed LaTeX (unbalanced braces, unterminated environments,
   stray backslashes), **when** parsed, **then** the parser does not raise and
   returns a best-effort structure.
8. **Given** identical content parsed twice with caching enabled, **when**
   `build_project_map` runs again, **then** results are identical and the cached
   path is used (same `content_hash`), with no behavioural difference vs cache
   off.

## 8. Test plan

> Suite stays under 2 minutes. The parser and context builder are pure/fast; the
> agent is exercised with a FakeLLM and deterministic fixtures.

- **Unit (pytest):**
  - `parse_latex_structure`: table-driven fixtures covering all sectioning
    levels + nesting, starred variants, `\label` capture, comments, verbatim/
    lstlisting opacity, environments, `\input`/`\include`/`\subfile` detection,
    and range-boundary correctness (section ends before next peer).
  - Malformed-input robustness (no exceptions; best-effort output).
  - `locate_section`: synonyms, ordinals/positions, label queries, no-match,
    ranking/scoring determinism.
  - `select_context`: budget never exceeded; priority ordering; deterministic
    truncation with marker; surrounding-lines config respected.
  - `build_project_map`: multi-file stitching, `main_file` detection, include
    cycle guard, unresolved targets, content-hash caching (memory) gives
    identical results with/without cache.
- **Integration (pytest):**
  - Spec-42 `locate_section` tool, run inside the agent graph with a **FakeLLM**
    that requests one tool call, returns the structure-aware range for a fixture
    project. Assert the tool result contract matches spec 42 and the range is
    correct.
- **E2E:** none required for this spec (no UI); covered indirectly by spec 49's
  evals and spec 46/47 e2e.
- **Performance/budget note:** Pure-Python linear scans over small fixtures; the
  token counter is a deterministic stub (no tiktoken/network); caching keeps
  repeat parses cheap. No real LLM.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (`ruff`, `mypy`/`pyright`).
- [ ] New env vars documented in `.env.example`; docs updated if needed.
- [ ] No Overleaf code copied — the lezer-latex grammar was used for conceptual
      understanding only; the parser is an independent implementation.
