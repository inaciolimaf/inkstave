# Spec 13 — Document content API (requirements)

## 1. Summary

This spec adds storage and CRUD for the **text content** of documents — the
`.tex`/text source that a `doc` tree-entity represents. Content is stored as a
single UTF-8 text blob plus an integer `version` in a `documents` table keyed 1:1
to the tree `doc` entity. Two endpoints — get content and replace content — give
a single-user save baseline with **optimistic version checking**. Real-time
collaboration (Phase 4) later layers a CRDT over this same content.

## 2. Context & dependencies

- **Depends on:** **12** (`tree_entities`, type `doc`, ownership scoping),
  **11/02/03/04/08**.
- **Unlocks:**
  - **18/19** — editor opens and autosaves document content via this API.
  - **21/22** — the compiler reads document content to assemble the build dir.
  - **28+** — CRDT backend seeds/persists from this content + version.
  - **41–48** — the AI agent reads document content and proposes diffs against it.
- **Affected areas:** backend (model, schemas, service, router, migration);
  small extension to spec 12's create-doc flow (create an empty content row).

## 3. Goals

- A `documents` table (1:1 with a `tree_entities` row of type `doc`) holding full
  text + a monotonically increasing integer `version` + size metadata.
- `GET` content (returns text + version + metadata).
- `PUT` content (replace whole document) with **optimistic concurrency**: caller
  passes the version they based their edit on; a mismatch yields `409`.
- Creating a `doc` (spec 12) creates an empty content row (version 0).
- Size guard (max document bytes) returning a clear error.
- Alembic migration; unit + integration tests; suite < 2 min.

## 4. Non-goals (explicitly out of scope)

- CRDT / real-time / WebSocket sync, presence (Phase 4, 28+).
- Partial edits / patch/diff application (whole-document replace only here; the
  agent's hunk apply is spec 47, built on top of this).
- Version *history*: snapshots, diffs between versions, restore (Phase 5, 36+).
- Frontend editor or autosave (18/19).
- Binary file content (14).
- Per-line storage, ranges, comments, tracked changes.

## 5. Detailed requirements

### 5.1 Data model

**Decision — single text blob + integer version, 1:1 with the doc entity.**
Justification: simplest correct baseline; matches how the editor will send/receive
whole-document text in the REST phase; avoids premature line/range modelling
(Overleaf's docstore complexity) that the CRDT layer (Phase 4) will supersede
anyway. The `documents` row is a *satellite* of `tree_entities` (kept separate so
the tree table stays small and hot — see spec 12 §5.1).

#### Table `documents`

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `entity_id` | `UUID` | **PK**, FK → `tree_entities.id` `ON DELETE CASCADE` | 1:1 with a `doc` tree entity; the entity id *is* the PK (no separate id). |
| `project_id` | `UUID` | `NOT NULL`, FK → `projects.id` `ON DELETE CASCADE` | Denormalised for fast project-scoped queries/auth; kept consistent in service. |
| `content` | `TEXT` | `NOT NULL`, default `''` | Full UTF-8 source. |
| `version` | `INTEGER` | `NOT NULL`, default `0`, `CHECK (version >= 0)` | Optimistic-concurrency counter; +1 on every successful replace. |
| `size_bytes` | `INTEGER` | `NOT NULL`, default `0`, `CHECK (size_bytes >= 0)` | `len(content.encode("utf-8"))`; maintained on write. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` default `now()` | |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` default `now()`, `onupdate now()` | Bumped on every replace. |

**Constraints / invariants:**

- `entity_id` must reference a `tree_entities` row whose `type = 'doc'`. The DB
  can't easily enforce the referenced row's type; enforce in the **service**
  (creation only ever targets `doc` entities) and test it.
- A `documents` row exists **iff** its tree entity is a `doc`. Created when the
  doc entity is created (spec 12 flow, now extended) and removed by the FK cascade
  when the doc entity is deleted.

**Indexes:**

- PK on `entity_id`.
- `ix_documents_project_id` on `(project_id)` — list/scan a project's docs (used
  by compile assembly later).

**Relationships (SQLAlchemy):**

- `Document.entity` → `TreeEntity` (one-to-one; `uselist=False`). Add
  `TreeEntity.document` back-ref (lazy, explicit load).
- `Document.project` → `Project` (many-to-one).

**Project-create / doc-create extension.** Spec 12 creates `doc` tree entities.
**This spec extends that flow** so that creating a `doc` entity also inserts an
empty `documents` row (`content=''`, `version=0`, `size_bytes=0`) in the same
transaction. Provide `ensure_document(session, entity) -> Document` (idempotent)
for safety and for any docs created before this spec (migration backfill below).

**Migration:** one Alembic revision that (1) creates `documents` with constraints
and the project index, and (2) **backfills** an empty content row for every
existing `tree_entities` row of type `doc` that lacks one. Downgrade drops the
table. Reversible.

### 5.2 Backend / API

Router `app/api/v1/documents.py`, mounted under
`/api/v1/projects/{project_id}`. **All routes require auth** and the spec-11
ownership rule (`get_owned_project` dependency → `404 project_not_found` if not
the caller's). The `{entity_id}` must be a `doc` entity in that project.

**Pydantic schemas (`app/schemas/document.py`):**

```
DocumentContentRead:
    entity_id: UUID
    project_id: UUID
    version: int
    size_bytes: int
    content: str
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

DocumentContentReplace:
    content: str            # full new text; max size enforced (see config)
    base_version: int       # the version the client edited from (>= 0)
```

#### Endpoints

| # | Method | Path | Auth | Body | Success | Response |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `GET` | `/api/v1/projects/{project_id}/documents/{entity_id}` | required | — | `200` | `DocumentContentRead` |
| 2 | `PUT` | `/api/v1/projects/{project_id}/documents/{entity_id}` | required | `DocumentContentReplace` | `200` | `DocumentContentRead` (new version) |

**Behaviour details:**

1. **Get content** — resolves the `doc` entity in the project; returns its content
   row. If the entity exists but no `documents` row does (legacy/edge), lazily
   create an empty one and return it (`version=0`).
2. **Replace content (PUT)** — optimistic concurrency:
   - If `base_version == current version`: write `content`, set
     `version = current + 1`, recompute `size_bytes`, bump `updated_at`, return the
     new `DocumentContentRead` (with the incremented version). **200.**
   - If `base_version != current version`: **409 version_conflict**; the response
     body includes the current `version` and current `content` so the client can
     reconcile (return a `DocumentContentRead` of the server's current state under
     an `error.details.current` field per the spec-02 envelope, or as the 409
     body — pick one and document it; recommended: error envelope with
     `details: {current_version, server_content}`).
   - If `base_version > current version` (impossible normally): also `409`.
   - Content size > limit (config): **413 content_too_large**.
   - The update must be **atomic**: do it as a single `UPDATE ... WHERE entity_id=?
     AND version = :base_version RETURNING version` and treat 0 rows updated as the
     conflict case — this prevents lost updates under concurrency without a row
     lock round-trip. (Alternatively `SELECT ... FOR UPDATE` then update; the
     `WHERE version` form is preferred and must be tested for the lost-update case.)

**Error cases:**

| Condition | Status | `error.code` |
| --- | --- | --- |
| No/invalid token | `401` | `unauthorized` |
| Project missing/not owned/soft-deleted | `404` | `project_not_found` |
| Entity not found in project | `404` | `entity_not_found` |
| Entity exists but is not a `doc` (it's a folder/file) | `409` | `not_a_document` |
| `base_version` mismatch (concurrent edit) | `409` | `version_conflict` |
| Content exceeds max size | `413` | `content_too_large` |
| Bad UUID / malformed body | `422` | `validation_error` |

**Service layer (`app/services/document_service.py`):**

- `get_document(session, project_id, entity_id) -> Document` (creates empty row if
  the doc entity exists without one; raises `EntityNotFound`/`NotADocument`).
- `replace_content(session, project_id, entity_id, content, base_version)
  -> Document` — performs the version-checked atomic update; raises
  `VersionConflict(current_version, current_content)` on mismatch and
  `ContentTooLarge` over the limit.
- `ensure_document(session, entity) -> Document` (idempotent; used by spec-12
  doc-create flow and the migration backfill).

### 5.3 Frontend / UI

None (specs 18/19).

### 5.4 Real-time / jobs / external integrations

None. (CRDT/WebSocket is Phase 4 and will read/write the same `documents` rows.)

### 5.5 Configuration

New setting (Pydantic settings, with env var; add to `.env.example`):

- `MAX_DOCUMENT_BYTES` — default `2_000_000` (2 MB). Upper bound on a single
  document's UTF-8 byte length on replace. Documented in `.env.example` as
  `MAX_DOCUMENT_BYTES=2000000`.

## 6. Overleaf reference (study only — never copy)

> Inkstave stores a single Postgres text blob + version; Overleaf uses MongoDB
> line arrays with ranges in a dedicated docstore service. Study *save/version
> semantics*, not the storage shape.

- `services/docstore/app/js/DocManager.js` — how a document is fetched, updated,
  and how versioning/`rev` checks guard writes. Informs our optimistic
  `version`-checked replace.
- `services/docstore/app/js/RangeManager.js` — Overleaf's ranges (comments/tracked
  changes). Inkstave does **not** implement ranges here; noted only so you
  recognise what we are deliberately omitting.
- `services/web/app/src/Features/Documents/DocumentController.mjs` — the HTTP shape
  of get/set document endpoints and how project/doc ids are validated.

## 7. Acceptance criteria

1. **Given** a newly created `doc` entity (via spec 12), **when** the owner `GET`s
   its content, **then** `200` with `content == ""`, `version == 0`, `size_bytes == 0`.
2. **Given** a doc at version 0, **when** the owner `PUT`s `{content:"\\documentclass{article}", base_version:0}`,
   **then** `200`, the returned `version == 1`, `content` matches, and `size_bytes`
   equals the UTF-8 byte length.
3. **Given** a doc at version 1, **when** a client `PUT`s with `base_version:0`,
   **then** `409 version_conflict`, the document is unchanged (still version 1),
   and the response carries the server's current version and content.
4. **Given** two concurrent replaces both based on version 1, **then** exactly one
   succeeds (→ version 2) and the other gets `409` — no lost update (verified via
   the `WHERE version` atomic update path).
5. **Given** content larger than `MAX_DOCUMENT_BYTES`, **when** PUT, **then**
   `413 content_too_large` and no change.
6. **Given** a `folder` or `file` entity id, **when** GET/PUT content on it,
   **then** `409 not_a_document` (or `404 entity_not_found` if the id doesn't
   exist at all).
7. **Given** user A's project, **when** user B calls either endpoint, **then**
   `404 project_not_found` (ownership = existence).
8. **Given** a doc with content, **when** its tree entity is deleted (spec 12),
   **then** the `documents` row is gone (FK cascade) — verified.
9. The migration applies/rolls back cleanly and backfills empty content rows for
   pre-existing `doc` entities. Suite stays under 2 minutes.

## 8. Test plan

> Fast, DB-only.

- **Unit (pytest):**
  - `replace_content` version logic: equal/greater/less `base_version`; size limit;
    `size_bytes` recomputation incl. multibyte UTF-8 (e.g. `é`, emoji) byte counting.
  - `ensure_document` idempotency.
  - `NotADocument` raised for folder/file entity.
- **Integration (pytest + httpx + Postgres):**
  - Create doc → empty content; PUT v0→v1; GET reflects new content/version.
  - Conflict: stale `base_version` → 409 with server state.
  - Lost-update simulation: two replaces on the same base version (sequential
    against the atomic `WHERE version` update) → one 200, one 409.
  - Size limit → 413.
  - Wrong entity type → 409; missing entity → 404; cross-user → 404.
  - Cascade: delete the doc tree entity → content row removed.
  - Migration up/down + backfill smoke.
- **E2E (Playwright):** none (no UI yet).
- **Performance/budget note:** documents in tests are tiny; no external I/O. The
  2 MB limit is tested by constructing a string near the boundary (cheap).

## 9. Definition of Done

- [ ] All requirements in §5 implemented (model, service, router, doc-create
      extension, migration + backfill).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] `MAX_DOCUMENT_BYTES` documented in `.env.example`.
- [ ] No Overleaf code copied.
