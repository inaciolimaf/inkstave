# ADR 0011 — Projects use soft delete

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 11 — Project model & CRUD API

## Context

Projects are the top-level container that the file tree (12), document content
(13), binary files (14), compile outputs, history (36–38) and sharing (33) all
hang off. We need a deletion strategy that does not paint those later specs into
a corner.

## Decision

### Soft delete via a nullable `deleted_at`

`DELETE /api/v1/projects/{id}` sets `deleted_at = now()` instead of removing the
row. Every read/list/rename path filters `WHERE deleted_at IS NULL`, so a
soft-deleted project is invisible: a follow-up `GET`/`PATCH`/`DELETE` returns
**404 `project_not_found`**, and it disappears from listings.

- **Why not hard delete now:** a cascading hard delete would destroy child rows
  (tree entities, documents, files, compile outputs, history) that do not exist
  yet. A real **purge job** that tombstones-then-deletes is deferred to a later
  spec; this keeps spec 11 non-destructive.
- **Future UX:** a "trash"/restore flow and history/sharing features become a
  pure read-filter change, with no second migration to add the column.
- **Listing performance:** a **partial** index
  `ix_projects_owner_active (owner_id, updated_at DESC) WHERE deleted_at IS NULL`
  keeps the hot "my active projects, recent first" query efficient and small
  (soft-deleted rows are excluded from the index).

### Ownership equals existence (404, never 403)

All endpoints are owner-scoped. A project owned by another user — or
soft-deleted, or non-existent — is **indistinguishable**: always `404`, never
`403`, never the project body. `get_owned_project` enforces this with a single
query filtering `id == … AND owner_id == … AND deleted_at IS NULL`, so existence
is never leaked.

### `updated_at` advances on rename — `clock_timestamp()`

Rename sets `updated_at = clock_timestamp()` rather than relying on the mixin's
`onupdate=now()`. PostgreSQL `now()` returns the **transaction start** time, which
is constant within a transaction (and the test harness runs each test in one
rolled-back transaction), so two updates in the same transaction would share a
timestamp. `clock_timestamp()` is the real wall clock and advances within a
transaction, guaranteeing `updated_at` strictly increases on every rename. This
is localized to the project rename to avoid changing the shared `TimestampMixin`.

### Owner FK is `ON DELETE CASCADE`

`projects.owner_id → users.id ON DELETE CASCADE`: deleting a user removes their
projects at the DB level (and the SQLAlchemy relationship mirrors this with
`cascade="all, delete-orphan", passive_deletes=True`). This is a hard cascade by
design — a removed account should not leave orphaned projects — and is distinct
from the per-project **soft** delete above.

## Consequences

- `projects` carries `deleted_at TIMESTAMPTZ NULL`; all queries filter it.
- No new env vars. Page size is a router constant (`limit` 1–100, default 50).
- Later specs add child tables referencing `projects.id`; a purge job (separate
  spec) will own true row removal.

## Alternatives considered

- **Hard delete now** — simplest, but destructive and would need rework once
  child tables exist; rejected.
- **A separate `deleted_projects` tombstone table** (Overleaf-style) — more
  moving parts than a `deleted_at` flag buys at this stage; rejected for the flag.
- **Changing the shared `TimestampMixin` to `clock_timestamp()`** — broader blast
  radius across all tables; rejected in favour of the localized rename change.
