# Spec 43 — Agent Diff Generation (requirements)

## 1. Summary

This spec turns the agent's **staged edits** (`StagedEdit`s produced by spec 42's
`propose_edit`) into **reviewable, per-file unified diffs**. For each target
document it computes a unified diff between the document's **current content** and
the proposed content, breaks it into individually-addressable **hunks**, records
the **base version** the diff was computed against (so the system can detect when
the document changed underneath the proposal), and persists everything in a new
`proposed_diffs` table. **Nothing is applied automatically** — application is
spec 47. After this spec, completing an agent turn that staged edits yields stored
`proposed_diffs` rows ready for streaming (44) and review (47).

## 2. Context & dependencies

- **Depends on:**
  - **42** — `StagedEdit` entries in `AgentState.staged_edits` (with `doc_id`,
    `mode`, `new_text`, range, `base_version`, `rationale`), and the tool/registry
    plumbing.
  - **41** — sessions/messages, the runner, `AgentDeps`.
  - **13** — current document content + version marker.
- **Unlocks:**
  - **44** — emits `diff_proposed` events carrying these rows' ids.
  - **47** — renders hunks, accepts/rejects per hunk, applies accepted hunks via
    the document API; uses `base_version` to detect drift.
- **Affected areas:** backend (`agent/diffs/` module, repository), database (one
  new table `proposed_diffs` + Alembic migration), tests. Docs: one ADR.

## 3. Goals

- Compute a **per-file unified diff** from each group of staged edits for a doc:
  apply the staged edits to an in-memory copy of current content to produce the
  *proposed* content, then diff `current` vs `proposed`.
- Model the diff as an ordered list of **hunks**, each with old/new line ranges,
  the unified-diff hunk header, the hunk body, and a stable `hunk_id`, so the UI
  (47) can accept/reject **per hunk**.
- Track the **base version** (`base_version`) the diff was computed against and a
  content hash, enabling **drift detection** at review time.
- Persist a `proposed_diffs` row per (session, doc) with status lifecycle.
- Guarantee **no document mutation** occurs in this spec.
- Provide a function `materialize_diffs(state, ctx) -> list[ProposedDiff]` the
  runner calls after the graph finishes a turn.

## 4. Non-goals (explicitly out of scope)

- **Applying** accepted hunks back to documents — spec 47 (endpoint + UI).
- **Per-hunk accept/reject UI** — spec 47.
- **Streaming `diff_proposed` events / ARQ** — spec 44.
- **Conflict *resolution*** — this spec only *detects* drift (stale base);
  rebasing/merging strategies are out of scope (47 may re-request).
- **Word-level / intra-line diff rendering** — line-based unified diff only; any
  richer rendering is the UI's concern (47/38).

## 5. Detailed requirements

### 5.1 Data model

New table `proposed_diffs`. Follow spec 03 conventions; one Alembic migration.

| Column | Type | Constraints / notes |
| --- | --- | --- |
| `id` | UUID | PK |
| `session_id` | UUID | FK → `agent_sessions.id` ON DELETE CASCADE; NOT NULL; indexed. |
| `message_id` | UUID | FK → `agent_messages.id` ON DELETE SET NULL; nullable; the assistant message/turn that produced it (for traceability). |
| `project_id` | UUID | FK → `projects.id` ON DELETE CASCADE; NOT NULL; indexed (authz + listing). |
| `doc_id` | UUID | FK → documents (spec 13) ON DELETE CASCADE; NOT NULL; indexed. One row per (session turn, doc). |
| `path` | text | NOT NULL; document path snapshot at proposal time. |
| `base_version` | text | NOT NULL; the doc version/revision the diff was computed against (from 13). |
| `base_hash` | text | NOT NULL; hash (e.g. sha256 hex) of the exact base content used, for robust drift detection even if versions are coarse. |
| `diff_text` | text | NOT NULL; the full **unified diff** for the file (standard `---/+++/@@` format). |
| `hunks` | JSONB | NOT NULL; ordered array of hunk objects (see 5.2.2). |
| `stats` | JSONB | NOT NULL; `{additions, deletions, hunk_count}`. |
| `status` | enum `proposed_diff_status` | NOT NULL, default `proposed`. Values: `proposed`, `applied`, `partially_applied`, `rejected`, `stale`, `superseded`. |
| `rationale` | text | nullable; combined rationale from staged edits. |
| `created_at` | timestamptz | NOT NULL default now. |
| `updated_at` | timestamptz | NOT NULL default now. |

Indexes: `(session_id, created_at)`, `(project_id, status)`, `(doc_id)`.

> Status transitions (this spec only *creates* `proposed`; 47 drives the rest):
> `proposed → applied | partially_applied | rejected | stale | superseded`.
> A row becomes `stale` when, at apply time (47), the current doc version/hash no
> longer matches `base_version`/`base_hash`. `superseded` when a newer proposal
> for the same doc in the same session replaces it.

### 5.2 Backend / modules

```
agent/diffs/
├── __init__.py
├── compute.py      # build proposed content from StagedEdits; unified diff; hunks
├── models.py       # SQLAlchemy ProposedDiff model
├── schemas.py      # Pydantic Hunk, ProposedDiffOut, DiffStats
└── repository.py   # persist + query proposed diffs
```

#### 5.2.1 Computing proposed content

`apply_staged_edits(current_text, edits) -> str`:

- Group the turn's `StagedEdit`s **by `doc_id`** (done by the caller); within a
  doc, apply edits to produce the proposed content:
  - `mode="full"`: proposed content = `new_text` (whole-doc replacement).
  - `mode="range"`: replace lines `[start_line, end_line)` (0-based, end
    exclusive) with `new_text` (split into lines preserving the document's
    newline convention).
- If multiple `range` edits target one doc, they must be **non-overlapping**;
  apply them **bottom-up** (highest `start_line` first) so earlier indices stay
  valid. **Overlapping** ranges for the same doc → raise/record a
  `DiffConflictError` and mark that file's proposal `rejected` with a reason
  (the agent shouldn't have proposed overlapping ranges; surfaced to the user).
- A `full` edit combined with any `range` edit on the same doc → treat `full` as
  authoritative and ignore the ranges (record a note); or reject — choose one and
  document it. **Default: `full` wins, ranges ignored, note recorded.**
- Preserve a trailing newline iff the current content had one (avoid a spurious
  "\ No newline at end of file" churn).

#### 5.2.2 Unified diff + hunk model

Use Python's `difflib.unified_diff` (or equivalent) over `current` vs `proposed`
line lists, with a small fixed context (e.g. 3 lines). Produce:

`diff_text`: the standard unified diff with headers
`--- a/<path>` / `+++ b/<path>`.

`hunks`: ordered array; each hunk:

```json
{
  "hunk_id": "h1",                 // stable within this diff (sequential)
  "header": "@@ -12,6 +12,8 @@",
  "old_start": 12, "old_lines": 6,
  "new_start": 12, "new_lines": 8,
  "lines": [                       // each line carries its origin
    {"op": " ", "text": "context line"},
    {"op": "-", "text": "removed line"},
    {"op": "+", "text": "added line"}
  ],
  "additions": 2, "deletions": 1
}
```

- Line numbers are **1-based** in hunk headers (standard unified-diff convention),
  even though `StagedEdit` ranges are 0-based — convert carefully and test it.
- `hunk_id`s are stable and ordered (`h1, h2, …`) so spec 47 can accept/reject
  individual hunks and reconstruct a partial apply.
- If `current == proposed` (no-op edit), produce **no** `proposed_diffs` row for
  that doc and record a note (the agent proposed a change identical to current).

#### 5.2.3 Base-version & drift tracking

- At computation time, capture `base_version` (from 13's version marker for the
  doc) and `base_hash = sha256(current_text)`. Store both.
- Provide `is_stale(diff, current_text, current_version) -> bool`: true when the
  current doc no longer matches the stored base (version differs **or** hash
  differs). Spec 47 calls this at apply time and flips status to `stale` if so.
- This spec does **not** itself re-check staleness over time; it only records the
  base and exposes the predicate.

#### 5.2.4 Materialization entry point

`materialize_diffs(*, state, ctx, db, session, message_id) -> list[ProposedDiff]`:

1. Read `state.staged_edits`; group by `doc_id`.
2. For each doc: fetch current content + version (13) **freshly** (authoritative),
   compute proposed content, compute diff + hunks + stats, capture base
   version/hash.
3. Skip docs whose diff is empty (no-op).
4. Mark any **prior** `proposed` rows for the same (session, doc) as `superseded`.
5. Insert one `proposed_diffs` row per changed doc with `status="proposed"`.
6. Return the created rows.

The spec-41/44 runner calls `materialize_diffs` **after** the graph finishes,
passing the assistant message id of the turn. Persisting diffs is part of the
turn's transaction (or a clearly-defined follow-on); **no document is written**.

#### 5.2.5 Read API for diffs (module-level, not HTTP)

Repository query helpers used by 44/47:

- `list_for_session(session_id) -> list[ProposedDiff]`
- `list_open_for_project(project_id) -> list[ProposedDiff]` (status `proposed`)
- `get(diff_id) -> ProposedDiff | None`
- `set_status(diff_id, status, *, applied_hunk_ids=None)` (used by 47).

HTTP exposure of these is spec 44; do **not** add routes here.

### 5.3 Frontend / UI

None. (Diff review UI is spec 47; concepts may be shared with spec 38's history
diff viewer but are implemented there independently.)

### 5.4 Real-time / jobs / external integrations

- No LLM, no network, no ARQ in this spec. Pure computation + DB writes.
- Spec 44 will emit a `diff_proposed` event per created row (id, doc_id, path,
  stats) after `materialize_diffs` runs inside the ARQ job.

### 5.5 Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `AGENT_DIFF_CONTEXT_LINES` | `3` | Unified-diff context lines per hunk. |
| `AGENT_DIFF_MAX_DOC_CHARS` | `400000` | Refuse to diff documents larger than this (return a single "file too large to diff" note instead of a row). |

Add to `AgentSettings` and `.env.example`.

## 6. Overleaf reference (study only — never copy)

> **No Overleaf reference for the agent.** Overleaf has no AI agent and no
> proposed-diff workflow — nothing to copy or translate. Inkstave's **own** spec
> 38 (history diff viewer) covers *line diff rendering* concepts and may inform
> the hunk model, but it is an independent Inkstave implementation, not Overleaf
> code, and this spec must not couple tightly to it. Use Python's standard
> `difflib` for the diff itself.

## 7. Acceptance criteria

1. **Given** a document and a single `range` `StagedEdit` replacing lines
   `[3,5)`, **when** `materialize_diffs` runs, **then** one `proposed_diffs` row is
   created with a valid unified `diff_text`, ≥ 1 hunk whose 1-based header matches
   the change, correct `additions/deletions`, status `proposed`, and the document
   content in the DB is **unchanged**.
2. **Given** a `full` `StagedEdit` replacing the whole document, **then** the diff
   reflects a whole-file replacement and `stats.hunk_count` ≥ 1.
3. **Given** two **non-overlapping** `range` edits on one doc, **then** they are
   applied bottom-up and the resulting diff contains both changes correctly
   positioned (no index drift bug).
4. **Given** two **overlapping** `range` edits on one doc, **then** computation
   records a conflict and that file's proposal is not silently mis-applied (it is
   rejected with a reason); no document is mutated.
5. **Given** a staged edit whose proposed content **equals** current content,
   **then** **no** `proposed_diffs` row is created (no-op skipped).
6. **Given** a created diff row, **when** the underlying document is then changed
   (new version/hash), **then** `is_stale(...)` returns `true` (and a subsequent
   apply in 47 would mark it `stale`). When unchanged, `is_stale` is `false`.
7. **Given** a prior `proposed` row for (session, doc) and a new proposal for the
   same pair in the same session, **then** the prior row is marked `superseded`
   and the new row is `proposed`.
8. **Given** the hunk model, **then** each hunk has a stable ordered `hunk_id`,
   per-line `op` in `{" ", "-", "+"}`, and correct `old_start/old_lines/
   new_start/new_lines`, such that applying only selected hunks (spec 47) is
   reconstructable.
9. **Given** a document larger than `AGENT_DIFF_MAX_DOC_CHARS`, **then** no row is
   created and a clear "too large" note is recorded instead of failing the turn.

## 8. Test plan

> Suite under 2 minutes. No LLM and no network in this spec at all; diff
> computation is pure and fast. Persistence uses the test DB.

- **Unit (pytest):**
  - `apply_staged_edits`: full replacement; single range; multiple non-overlapping
    ranges applied bottom-up (AC 3); overlapping ranges → conflict (AC 4); newline
    preservation; full-vs-range precedence note.
  - Unified diff + hunk parsing: header line numbers (0-based range → 1-based
    header conversion), per-line `op`, additions/deletions counts (AC 1, 2, 8).
  - No-op edit → no diff (AC 5).
  - `is_stale` true/false on version/hash change (AC 6).
  - Oversized doc handling (AC 9).
- **Integration (pytest + test DB):**
  - `materialize_diffs` from a seeded `AgentState.staged_edits`: creates rows,
    correct stats/status, **document content unchanged** in DB (AC 1).
  - Superseding prior proposals (AC 7).
  - Migration up/down for `proposed_diffs`.
- **E2E (Playwright):** none (no UI yet).
- **Performance/budget note:** pure `difflib` over small fixtures; no model, no
  network, no sleeps.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`; ADR added for hunk model +
      drift strategy if non-trivial.
- [ ] No document content is mutated by this spec.
- [ ] No Overleaf code copied (there is none for the agent).
