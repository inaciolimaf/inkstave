# Spec 42 — Agent Tools (requirements)

## 1. Summary

This spec gives the spec-41 agent a set of **typed tools** it can call from the
LangGraph `act` node. Each tool has a name, a Pydantic input schema, a structured
output, and explicit error handling. The tools are: `search_project`,
`read_file`, `list_tree`, `locate_section`, and `propose_edit`. All tools are
**read-only against the project** except `propose_edit`, which only **stages** a
proposed change into agent state (the actual diff is computed and stored in spec
43). Every tool runs **inside a single project the user can access** and enforces
that authorization. After this spec the agent can explore a real project and
stage edit intents under a `FakeLLM` that scripts tool calls.

## 2. Context & dependencies

- **Depends on:**
  - **41** — `AgentDeps`, `AgentState`, the empty tool registry hook, the `act`
    node, the `LLMClient`/`FakeLLM` (which can script `tool_calls`), and the
    `ToolSpec`/`ToolCall` types.
  - **12** — file-tree model: folders/docs/files, stable ids, paths, the service
    to read the tree and resolve a path → node.
  - **13** — document content storage & CRUD: fetch a document's current content
    and its version/revision marker.
- **Unlocks:**
  - **43** — consumes the `propose_edit` staged intents to build diffs.
  - **44** — emits `tool_call`/`tool_result` stream events from these tools.
  - **48** — replaces the `locate_section` heuristic with a real parser.
- **Affected areas:** backend (`agent/tools/` package, registry, authorization),
  tests; **no migration** (uses 41's schema + 12/13's existing tables).

## 3. Goals

- Define a **Tool abstraction**: name, description, Pydantic `args_schema`, an
  async `run(args, ctx) -> ToolResult`, and a method to emit a JSON-Schema
  `ToolSpec` (for the LLM `tools` parameter).
- Implement a **ToolRegistry** that the spec-41 graph receives via `AgentDeps`;
  the `act` node looks tools up by name, validates args, runs them, and appends a
  `role="tool"` message with the structured result.
- Implement a **ToolContext** carrying `project_id`, `user_id`, the DB session,
  and references to the 12/13 services — the single place authorization is
  enforced.
- Implement the five tools with precise schemas, outputs, size limits, and error
  results (errors are returned as structured `ToolResult`s, **never** raised into
  the graph).
- Implement **authorization**: every tool call is constrained to the session's
  project; any attempt to reference another project/file id is denied.
- Keep the suite green and under budget; no real LLM, no real network.

## 4. Non-goals (explicitly out of scope)

- **Diff text / hunks / `proposed_diffs` table** — spec 43. `propose_edit` here
  outputs a *staged edit intent* only.
- **HTTP/streaming/ARQ** — spec 44.
- **Rich LaTeX AST / cross-file section resolution** — spec 48. `locate_section`
  is a line-scan heuristic only.
- **Applying edits to documents** — never in the agent; spec 47 applies accepted
  diffs through the normal document API.
- **Binary file content tools** — `read_file` targets text documents (spec 13);
  binary files (spec 14) are listed by `list_tree` but their bytes are not read.

## 5. Detailed requirements

### 5.1 Data model

No new tables. `propose_edit` stages intents into the **in-memory** `AgentState`
(a `staged_edits` list) and, via the assistant/tool message records from spec 41,
the call is auditable. Spec 43 introduces the `proposed_diffs` table.

Extend `AgentState` (additive; no migration) with:

```python
staged_edits: list[StagedEdit]   # appended by propose_edit; consumed by spec 43
```

`StagedEdit` (Pydantic v2):

| Field | Type | Notes |
| --- | --- | --- |
| `edit_id` | str (uuid4) | stable id for this staged edit within the turn |
| `doc_id` | str | target document id (must be in the session's project) |
| `path` | str | document path (for display/logging) |
| `base_version` | str \| int | the document version/revision the edit was authored against (from spec 13) |
| `mode` | enum `full` \| `range` | `full` = replacement content for the whole doc; `range` = replace `[start_line, end_line)` |
| `new_text` | str | replacement text |
| `start_line` | int \| null | required when `mode="range"`, 0-based inclusive |
| `end_line` | int \| null | required when `mode="range"`, 0-based exclusive |
| `rationale` | str \| null | short why, surfaced later in the UI |

> `StagedEdit` deliberately does **not** contain a diff. It is the *input* to spec
> 43, which computes the unified diff against current content and stores it.

### 5.2 Backend / modules

```
agent/tools/
├── __init__.py        # registry assembly: default_registry(services)
├── base.py            # Tool, ToolContext, ToolResult, ToolRegistry
├── search_project.py
├── read_file.py
├── list_tree.py
├── locate_section.py
└── propose_edit.py
```

#### 5.2.1 Tool abstraction (`base.py`)

```python
class ToolContext(BaseModel, arbitrary_types_allowed=True):
    project_id: str
    user_id: str
    db: AsyncSession
    tree_service: FileTreeService     # from spec 12
    doc_service: DocumentService      # from spec 13
    # (no network, no LLM here)

class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None   # tool-specific payload when ok
    error: ToolError | None = None       # set when ok=False

class ToolError(BaseModel):
    code: Literal[
        "not_found", "forbidden", "invalid_args",
        "too_large", "unsupported", "internal",
    ]
    message: str

class Tool(ABC):
    name: str
    description: str
    Args: type[BaseModel]                # Pydantic input schema

    def spec(self) -> ToolSpec: ...       # name + description + JSON schema of Args
    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...

class ToolRegistry:
    def register(self, tool: Tool) -> None: ...
    def get(self, name: str) -> Tool | None: ...
    def specs(self) -> list[ToolSpec]: ...   # passed to LLMClient.complete(tools=...)
```

Rules:

- `run` **must not raise** for expected failures — it returns
  `ToolResult(ok=False, error=...)`. Only truly unexpected exceptions bubble; the
  `act` node catches them and converts to `code="internal"`.
- Each tool's `data` payload is **bounded** (see per-tool limits) so a tool result
  can never blow the LLM context. Truncation is explicit and flagged
  (`truncated: true`).
- The `act` node (spec 41) integration: for each `pending_tool_call`, validate
  arguments against `tool.Args`; on validation failure return a `tool` message
  with `invalid_args`. Append one `role="tool"` message per call with the
  JSON-serialized `ToolResult` as content and the matching `tool_call_id`.

#### 5.2.2 Authorization (single-project scope)

- `ToolContext.project_id` is fixed to the **session's** project (set by the
  runner in spec 41/44). Tools must:
  - Resolve any `doc_id`/`node_id`/`path` **within** `project_id`; if the id
    belongs to another project or doesn't exist in this project → `not_found`
    (do not leak existence) — but if it exists and the user lacks access →
    `forbidden`.
  - Re-check the user's access to the project via the access-control rules
    established in spec 34 (owner/editor/viewer). A **viewer** may use read tools
    (`search_project`, `read_file`, `list_tree`, `locate_section`) but
    `propose_edit` requires at least **editor** (proposing a change the user
    couldn't themselves apply is pointless) → otherwise `forbidden`.
- There is **no** "switch project" tool. The agent cannot escape its project.

#### 5.2.3 Tool: `search_project`

- **Purpose:** find files/sections by keyword across the project's text documents.
- **Args:**
  - `query: str` (1..200 chars, required)
  - `max_results: int = 20` (1..50)
  - `path_glob: str | null = null` (optional filter, e.g. `chapters/*.tex`)
- **Behavior:** case-insensitive substring/keyword match over document contents
  (line-level) and over file paths. Return ranked matches.
- **Output `data`:**
  ```json
  {
    "matches": [
      {"doc_id": "...", "path": "main.tex", "line": 42,
       "snippet": "...the introduction discusses...",
       "kind": "content" | "path" | "section"}
    ],
    "truncated": false
  }
  ```
- **Limits:** at most `max_results` matches; each `snippet` ≤ 240 chars; total
  payload soft-capped (e.g. 8 KB) → set `truncated:true` when cut. For `kind:
  "section"`, surface matches where the query hits a `\section{...}`-like title.
- **Errors:** `invalid_args` for empty query; otherwise always `ok=True` (no
  matches → empty list).

#### 5.2.4 Tool: `read_file` / `read_document`

- **Purpose:** read a text document's current content.
- **Args (one of):**
  - `doc_id: str` **or** `path: str` (exactly one required).
  - `start_line: int | null`, `end_line: int | null` (optional window, 0-based,
    `end` exclusive) to read a slice.
- **Behavior:** resolve within the project (12/13), fetch current content and its
  `version` marker (13). Return content (or the requested slice) with line
  numbers and the version.
- **Output `data`:**
  ```json
  {"doc_id":"...","path":"...","version":"...","start_line":0,
   "end_line":120,"line_count":120,"content":"...","truncated":false}
  ```
- **Limits:** hard cap on returned characters (e.g. 40 000); if the whole doc
  exceeds it and no window is given, return the first N lines with
  `truncated:true` and the true `line_count`, instructing (in `message`-style
  hint) to request a range.
- **Errors:** `invalid_args` (neither/both selectors, bad range), `not_found`
  (no such doc in project), `unsupported` (target is a binary file, not a text
  document), `forbidden` (no access).

#### 5.2.5 Tool: `list_tree`

- **Purpose:** enumerate the project file tree so the agent knows what exists.
- **Args:**
  - `path: str | null = null` (subtree root; default = project root)
  - `depth: int = 3` (1..10)
- **Output `data`:** a nested or flattened listing of nodes with
  `{node_id, path, type: folder|doc|file, size?, is_binary?}`, bounded to a max
  node count (e.g. 500) with `truncated`.
- **Errors:** `not_found` (path not in project), `forbidden`.

#### 5.2.6 Tool: `locate_section`

- **Purpose:** find a LaTeX sectioning unit by human name (e.g. "introduction",
  "methods", "related work") — **basic heuristic** now.
- **Args:**
  - `name: str` (1..120) — the section to find.
  - `doc_id: str | null = null` — restrict to one document; default: search the
    project's text docs (typically `main.tex` + chapter files).
- **Heuristic (documented, replaced by spec 48):**
  - Scan for `\part`, `\chapter`, `\section`, `\subsection`, `\subsubsection`
    (and starred variants) plus `\section*{}`. Extract the title.
  - Match `name` against titles case-insensitively, ignoring surrounding
    whitespace and a leading article ("the"); prefer exact title match, then
    substring, then a token-overlap score.
  - The section **range** is from the matched heading line to the next heading of
    the same-or-higher level (or EOF).
- **Output `data`:**
  ```json
  {"matches":[
    {"doc_id":"...","path":"...","level":"section","title":"Introduction",
     "heading_line":12,"start_line":12,"end_line":58,"score":1.0}],
   "method":"heuristic-v1"}
  ```
- **Errors:** `invalid_args` (empty name); else `ok=True` with possibly-empty
  `matches`. `not_found` only if a given `doc_id` isn't in the project.

#### 5.2.7 Tool: `propose_edit`

- **Purpose:** **stage** a proposed change to a document. Does **not** apply it
  and does **not** compute a diff (that is spec 43). Produces a `StagedEdit`.
- **Args:**
  - `doc_id: str` (required; must be in project)
  - `mode: "full" | "range"` (required)
  - `new_text: str` (required; bounded, e.g. ≤ 200 000 chars)
  - `start_line: int | null`, `end_line: int | null` (required iff `mode="range"`)
  - `rationale: str | null` (≤ 500 chars)
- **Behavior:**
  - Authorize **editor+** (per 5.2.2).
  - Resolve the doc and read its **current `version`** (13); set this as the
    `StagedEdit.base_version` so spec 43 can detect drift.
  - Validate the range against the current line count when `mode="range"`.
  - Append a `StagedEdit` to `AgentState.staged_edits` and return its `edit_id`.
- **Output `data`:**
  ```json
  {"edit_id":"...","doc_id":"...","path":"...","mode":"range",
   "base_version":"...","staged":true}
  ```
- **Errors:** `invalid_args` (missing range for range mode, range out of bounds,
  oversized `new_text`), `not_found`, `forbidden`, `unsupported` (binary target).
- **Important:** multiple `propose_edit` calls in one turn may target the same or
  different docs; spec 43 groups staged edits by `doc_id` into per-file diffs.

#### 5.2.8 Registry assembly

`default_registry(services) -> ToolRegistry` registers all five tools. `AgentDeps`
(from spec 41) is extended so `build_graph` receives this registry; the `act` node
now executes real tools instead of the spec-41 empty-registry fallback. The
fallback for an **unknown** tool name (model hallucination) is retained:
`ToolResult(ok=False, error=ToolError(code="unsupported", message="unknown tool"))`.

### 5.3 Frontend / UI

None. (Tool-call rendering in chat is spec 46; diff review is spec 47.)

### 5.4 Real-time / jobs / external integrations

- Tools call **only** Inkstave's own services from specs 12/13 (and access-control
  from 34) via the injected `ToolContext` — no external network, no LLM.
- Streaming of `tool_call`/`tool_result` events is spec 44; this spec just
  produces the structured results those events will carry.

### 5.5 Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `AGENT_TOOL_READ_MAX_CHARS` | `40000` | Char cap for `read_file` output. |
| `AGENT_TOOL_SEARCH_MAX_RESULTS` | `50` | Upper bound for `search_project.max_results`. |
| `AGENT_TOOL_TREE_MAX_NODES` | `500` | Node cap for `list_tree`. |
| `AGENT_TOOL_EDIT_MAX_CHARS` | `200000` | Char cap for `propose_edit.new_text`. |

Add these to `AgentSettings` and `.env.example`.

## 6. Overleaf reference (study only — never copy)

> **No Overleaf reference for the agent.** Overleaf has no AI agent and no tool
> framework — there is nothing to copy or translate. The only material to consult
> is Inkstave's **own** specs **12** (file-tree model) and **13** (document
> content API), because the read/search tools call those services. Use their
> public service contracts; do not reach around them into raw tables.

## 7. Acceptance criteria

1. **Given** a seeded project with `main.tex` containing
   `\section{Introduction}`, **when** `locate_section(name="introduction")` runs,
   **then** it returns one match with `title="Introduction"`, the correct
   `heading_line`, and an `end_line` at the next same-or-higher heading (or EOF).
2. **Given** the same project, **when** `search_project(query="introduction")`
   runs, **then** results include both a `kind:"section"` and/or `kind:"content"`
   match referencing `main.tex`, ranked, and capped at `max_results`.
3. **Given** a text document of 1 000 lines, **when** `read_file(doc_id=...)` is
   called with no window, **then** output is truncated to the configured char cap
   with `truncated:true` and the true `line_count`; **and** calling with
   `start_line/end_line` returns exactly that slice with `truncated:false`.
4. **Given** `list_tree(depth=2)`, **then** it returns project nodes with
   `node_id`, `path`, `type`, bounded to `AGENT_TOOL_TREE_MAX_NODES`.
5. **Given** an **editor** user, **when** `propose_edit` stages a `range` edit,
   **then** a `StagedEdit` is appended to `AgentState.staged_edits` with the
   document's **current** `version` as `base_version`, the tool returns
   `staged:true`, **and the document content is unchanged** in the DB.
6. **Given** a **viewer** user, **when** `propose_edit` is called, **then** the
   result is `ok=False, code="forbidden"`; read tools still succeed for the viewer.
7. **Given** a `doc_id` that belongs to a **different** project, **when** any tool
   references it, **then** the result is `not_found` (no cross-project leakage),
   and no content from that document is returned.
8. **Given** the `act` node and a `FakeLLM` that scripts a call to a tool name not
   in the registry, **then** the node returns a `tool` message with
   `code="unsupported"` and the graph continues safely (no crash, no loop blow-up).
9. **Given** any tool, **when** given arguments that fail its Pydantic schema,
   **then** it yields `ok=False, code="invalid_args"` and never raises into the
   graph.
10. **Given** a `propose_edit` with `mode="range"` whose `end_line` exceeds the
    document's line count, **then** the result is `invalid_args`.

## 8. Test plan

> Suite stays under 2 minutes. The LLM is always `FakeLLM`; tools run against a
> seeded **test database** (specs 12/13 fixtures) — no external network.

- **Unit (pytest):**
  - Each tool's `Args` schema validation (happy + `invalid_args`).
  - `locate_section` heuristic across headings, starred variants, articles
    ("the introduction"), and ranges to next heading (AC 1).
  - `search_project` ranking, snippet length, `truncated` behavior (AC 2).
  - `read_file` windowing + char-cap truncation (AC 3).
  - `ToolRegistry.specs()` produces valid JSON-Schema for each tool.
- **Integration (pytest + test DB):**
  - Seeded project; run each tool through `ToolContext`; verify outputs against
    real 12/13 services (AC 1–5).
  - Authorization matrix: owner/editor/viewer × read tools vs `propose_edit`
    (AC 6); cross-project id denial (AC 7).
  - `act`-node integration with a `FakeLLM` scripting tool calls: a real tool
    call produces a `role="tool"` message with the structured result; unknown
    tool → `unsupported` (AC 8); `propose_edit` leaves the document content
    unchanged in the DB (AC 5).
- **E2E (Playwright):** none (no UI yet).
- **Performance/budget note:** tools touch only the in-memory test DB; no LLM
  network; `FakeLLM` scripts deterministic tool calls so graph runs are instant.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`.
- [ ] No Overleaf code copied (there is none for the agent); read/search tools go
      through specs 12/13 services, not raw tables.
