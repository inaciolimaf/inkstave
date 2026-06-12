# ADR 0042 — Agent tools: registry shape, ToolContext, and the section locator

- **Status:** Accepted
- **Date:** 2026-06-11
- **Context spec:** 42 — Agent Tools (search / read / list / locate / propose)

## Context

Spec 41 landed the LangGraph scaffold with an empty tool registry. Spec 42 fills it
with five typed, project-scoped tools — `search_project`, `read_file`, `list_tree`,
`locate_section`, and `propose_edit` — that let the agent inspect a project and
**stage** (never apply) a change. Overleaf has no agent and no tool abstraction, so
this was built purely from the spec. This ADR records the design choices it made
that the spec called out as "notable" (README step 7), and — because it is the
nearest home — the suite-budget decision from the batch-10 fix-pack (spec 82).

## Decisions

### 1. `ToolContext` is a `@dataclass`, not a Pydantic `BaseModel`

Spec 42 §5.2.1 sketched `ToolContext` as a Pydantic `BaseModel`
(`arbitrary_types_allowed=True`) carrying explicit `tree_service`/`doc_service`
fields. Inkstave instead uses a plain `@dataclass` (`agent/tools/base.py`) holding a
single `db: AsyncSession` plus `project_id`/`user_id`/`settings`/`staged_edits` (and
the spec-49 `audit_events`/`injection_guard`). The spec-12/13 services are stateless
**module-level functions** over a session, so passing the `AsyncSession` is sufficient
DI: there are no per-turn service objects to construct or hold, and the context stays
a cheap dataclass with no Pydantic arbitrary-type plumbing. Tool **inputs/outputs**
remain Pydantic (`Args`, `ToolResult`, `ToolError`) where schema/validation actually
earns its keep — only the execution context is a dataclass. (The deviation is also
documented inline at the `ToolContext` docstring.)

### 2. Services are called module-level, not injected as objects

Following on from (1): tools `import` the spec-12 tree service and spec-13 document
service and call them as functions against `ctx.db`, rather than receiving
constructed service instances. This keeps wiring flat (no factory layer), matches how
the rest of the backend uses those services, and means a new tool only needs the
`ToolContext`. Authorization is re-checked per call via `authorize(ctx)` (project read,
plus `require_write` for `propose_edit`) so an `entity_id` is never trusted without the
session's project scope.

### 3. Expected failures are returned, never raised into the graph

Tools return `ToolResult(ok=False, error=ToolError(code, message))` for expected
conditions (`not_found`, `forbidden`, `invalid_args`, `too_large`, `unsupported`,
`internal`) instead of raising. The graph treats a tool result as data, so a bad
argument or a missing doc can never crash a turn — it becomes an observation the model
can react to.

### 4. `locate_section` is a heuristic, replaced in spec 48 — kept testable

Spec 42 specified `locate_section` as a **basic heuristic** (the rich LaTeX parser is
spec 48). It scored sectioning commands (`\section`, `\chapter`, …) by fuzzy name
match and returned line ranges. Spec 48 swapped the internals for the structure-aware
project map but kept the tool's surface; the result `method` label is intentionally
left as `"structure-v1"` (not a behaviour change — see ADR-0043/0048). The decision
worth recording here is that the locator is a *named, swappable* heuristic behind a
stable tool schema, so later specs can upgrade accuracy without changing the agent's
contract.

### 5. (Spec 82) Backend suite budget restored with `pytest-xdist -n auto`

The full backend suite drifted to ~3m01s single-threaded — over the `< 2 minutes` DoD
(spec 22 / spec 53). The tests themselves are fast in isolation; the regression is
purely the missing **parallelism** in the default/CI pytest path. The decision is to
run the backend suite with `pytest-xdist`'s `-n auto`, which brings it back under two
minutes on a multi-core machine with no test changes. The pytest config
(`pyproject.toml`/`pytest.ini`) and CI workflow are outside the spec-82 fix-pack's
file set, so this ADR records the required change; applying `-n auto` there is the
implementation step. Tests must stay isolation-safe (own DB/transaction per test,
no shared global state) for `-n auto` to be sound, which the current fixtures already
are.

## Consequences

- `inkstave.agent.tools` package: `base.py` (Tool/ToolContext/registry/authorize) plus
  one module per tool; the registry plugs into the spec-41 graph with no node changes.
- `ToolContext` being a dataclass keeps later specs (43 diffs, 44 streaming, 49 safety)
  free to add fields without Pydantic friction; they already added `staged_edits`,
  `audit_events`, and `injection_guard`.
- The suite-budget decision is operational, not code: enabling `-n auto` (and keeping
  tests isolation-safe) is what holds the `< 2 minutes` line as the suite grows.
