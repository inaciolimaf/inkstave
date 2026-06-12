# ADR 0043 — Agent diff generation: hunk model + drift strategy

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 43 — Agent Diff Generation

## Context

Spec 42's `propose_edit` stages `StagedEdit` intents into agent state. Spec 43 turns
those into reviewable per-file unified diffs and persists them, so spec 44 can stream
them and spec 47 can review/apply them hunk-by-hunk. Nothing is applied here.

## Decisions

### 1. Proposed content is built deterministically, then diffed

`apply_staged_edits(current_text, edits)` (one doc's edits) produces the proposed
content: a `full` edit replaces the whole doc and **wins over** any `range` edits
(ranges ignored, note recorded); multiple `range` edits must be non-overlapping and
are applied **bottom-up** (highest `start_line` first) so earlier indices stay valid.
**Overlapping** ranges raise `DiffConflictError` → that file's proposal is persisted
as a `rejected` row with a reason (never silently mis-applied). A trailing newline is
preserved iff the current content had one, to avoid spurious churn.

### 2. Hunks from `SequenceMatcher`, 1-based headers

`compute_diff` builds both `diff_text` and the structured `hunks` from
`difflib.SequenceMatcher.get_grouped_opcodes(context)` — one source so they never
disagree. Each hunk has a stable ordered `hunk_id` (`h1, h2, …`), the unified-diff
`header`, `old_start/old_lines/new_start/new_lines` (**1-based**, converted from the
0-based `StagedEdit` ranges via difflib's range-format convention), per-line `op`
in `{" ", "-", "+"}`, and additions/deletions counts — enough for spec 47 to apply a
selected subset of hunks. `current == proposed` yields no hunks → **no row** (no-op
skipped).

### 3. Drift detection by version *and* content hash

Each row records `base_version` (the doc's spec-13 version marker at compute time)
and `base_hash = sha256(current_text)`. `is_stale(diff, current_text, current_version)`
returns true when either differs — robust even if version bumps are coarse. This spec
only records the base and exposes the predicate; spec 47 calls it at apply time and
flips status to `stale`.

### 4. `materialize_diffs` is the single entry point, called by the runner

After the graph finishes a turn and messages are persisted, `run_turn` calls
`materialize_diffs(state, settings, db, session, message_id)` with the final
assistant message id. It fetches each doc's content/version **freshly**, computes the
diff, **supersedes** prior open `proposed` rows for the same (session, doc), and
inserts one `proposed → ` row per changed doc. Oversized docs
(`AGENT_DIFF_MAX_DOC_CHARS`) are skipped with a logged note. The created rows ride on
the turn's transaction; **no document is ever written**. (The spec sketched a `ctx`
parameter; we pass `settings` directly since that is all the function needs beyond
`db`/`session`.)

### 5. Persistence + status lifecycle

`proposed_diffs` (one row per session-turn × doc) carries `diff_text`, `hunks`
(JSONB), `stats`, `base_version`/`base_hash`, `rationale`, and a `status`
(`proposed | applied | partially_applied | rejected | stale | superseded`, enforced
by a CHECK constraint matching the codebase's enum convention). This spec creates only
`proposed`/`rejected`/`superseded`; spec 47 drives the rest via `repository.set_status`
(which also records `applied_hunk_ids` for partial applies).

## Consequences

- New `inkstave.agent.diffs` package (compute/models/schemas/repository + the
  `materialize_diffs` entry point) and the `proposed_diffs` table (migration
  `b8c1d5f47a69`). Two new env vars. `AgentTurnResult` gains `proposed_diffs`.
- 16 tests: pure diff/apply/drift as units; `materialize_diffs` (rows, stats,
  supersede, conflict→rejected, no-op skip, oversize skip, **doc unchanged**) as
  integration. No LLM, no network; suite ~52s.
