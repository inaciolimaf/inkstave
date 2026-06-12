# ADR 0048 — Agent context: structural LaTeX scan, project map, context budget

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 48 — Agent Context & LaTeX Section Parsing

## Context

The agent needs precise awareness of a LaTeX project so "edit the introduction"
resolves to the right file and range. Spec 48 replaces spec-42's `locate_section`
line-scan heuristic with a real structural parser, a cross-file project map, and
token-budget-aware context selection — all server-side, no DB, no embeddings.

## Decisions

### 1. A lightweight structural scanner, not a LaTeX parser

`parse_latex_structure(text, file_path)` is a single linear, line-by-line scan
(`inkstave.agent.context.parser`). It detects sectioning commands (`\part`…
`\subparagraph`, starred), notable environments, and `\input`/`\include`/`\subfile`,
mapping each to 1-based line + 0-based char ranges. It is independent of Overleaf's
lezer-latex grammar (read only for concepts). Robustness rules that the ACs hinge on:
**comments** are stripped (`%`, respecting `\%`); **verbatim-like** environments
(`verbatim`, `lstlisting`, `minted`, …) are **opaque** so a `\section` inside them is
not parsed; **starred** sections are captured; an immediately-following `\label{}` is
attached. It never raises on malformed input (unbalanced braces / unterminated
environments) — it degrades to best-effort. A sectioning node's range extends to just
before the next sibling-or-higher heading, giving each section a contiguous editable
span.

### 2. The project map stitches `\input` across files

`build_project_map(project_id, tex_paths, file_reader)` parses every `.tex` file via an
injected synchronous `file_reader`, detects `main_file` by `\documentclass`, and
**stitches** the outline: each `\input`/`\include`/`\subfile` is resolved (path,
`.tex`, project-root- and including-file-relative variants) and the target's outline
becomes that node's children. A `visiting` set guards include cycles; unresolvable
targets are recorded in `unresolved_inputs`. Results are cached by
`project_id:content_hash` in memory (optional; never changes results).

### 3. Deterministic, lexical section resolution

`locate_section(project_map, query)` ranks sections with no LLM: exact title (1.0),
`\label` (0.95), **synonym** concept match — derived from the whole phrase *and* each
token, so "methods section" → "method" matches "Methodology" (0.9) — substring (0.7),
then token overlap. **Ordinal/positional** queries ("section 2", "the first
subsection") resolve to the Nth node of that command. An unmatched query returns `[]`.

### 4. Context selection within a token budget

`select_context(project_map, file_reader, goal, budget_tokens)` builds prioritised
chunks — the target section's content + configurable surrounding lines (priority 0), a
compact outline summary (1), related-section pointers (2) — and greedily fits them
under the budget using an **injected** token counter (default `~4 chars/token`,
swappable for a real tokenizer). When a chunk overflows it is **deterministically
truncated** to whole lines with a `… [truncated]` marker; lower-priority chunks that
don't fit are dropped. The returned bundle's `estimated_tokens` is always ≤ budget.

### 5. Spec-42 `locate_section` tool delegates here

The tool now pre-reads each text document, builds the project map, and returns the
structure-aware matches. Its external contract is unchanged except that line numbers
are now correct **1-based** (the parser's) and `method` is `"structure-v1"` — an
accuracy improvement over the prior heuristic.

## Consequences

- New `inkstave.agent.context` package (models, parser, project_map, locate, select).
  Four new settings (`AGENT_CONTEXT_TOKEN_BUDGET`, `AGENT_CONTEXT_SURROUNDING_LINES`,
  `AGENT_SECTION_EXTRA_COMMANDS`, `AGENT_CONTEXT_CACHE`). No DB, no migration, no UI.
- 13 tests: parser (nesting/ranges, comments+verbatim+starred, labels/inputs,
  malformed robustness), locate (synonyms/ordinals/labels/no-match), select
  (budget/truncation/outline), project map (stitch/main/cycles/unresolved/cache), and
  the spec-42 tool run through the agent graph (structure-aware result). Pure, fast,
  FakeLLM-only.
