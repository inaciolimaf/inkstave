# Spec 37 — History API (requirements)

## 1. Summary

This spec exposes the version history captured in spec 36 over REST: list versions
and updates within a range, compute a text diff between two versions (or a version
and the live document), restore a document (and optionally a whole project) to a
past version **non-destructively** (a restore creates a *new* version and is applied
as a CRDT update into the live room — it never deletes history), and manage named
labels/checkpoints. It introduces one new table (`history_labels`) and a restore
mechanism that interoperates with the live pycrdt document from spec 28.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 36** — `history_chunks`, `history_updates`, blob offload, the
    `reconstruct_state(doc_id, version)` primitive, and the per-doc `version` counter.
  - **Spec 28/29** — the authoritative pycrdt document and the mechanism to inject a
    server-originated update into the live room so a restore propagates to all clients.
  - **Spec 34** — access control: project membership and roles (owner/editor/viewer).
  - **Spec 13** — document content (for "current" reconstruction and diff targets).
- **Unlocks:**
  - **Spec 38** — history UI (timeline, diff viewer, restore button, labels) consumes
    these endpoints.
- **Affected areas:** backend (history read service, diff service, restore service,
  labels CRUD, router), database (one new table + migration), docs (restore ADR).

## 3. Goals

- List a document's captured versions with author + timestamp, paginated and
  range-filterable, tolerating gaps left by spec-36 compaction.
- List the raw `history_updates` (metadata) in a version range for a document.
- Produce a **text diff** (line/word-level, unified-ish JSON) between any two versions,
  and between a version and the live current document.
- **Restore** a document to a chosen version by computing the delta from current →
  target text and applying it as a single CRDT update into the live room, yielding a
  new version. History is never destroyed.
- Restore an entire **project** to a version label by restoring each document that
  existed at that point (best-effort, transactional per document, reported per file).
- Create / list / delete **labels** (named checkpoints) attached to a (doc, version)
  or a project-level version marker.
- Enforce access control: viewers may read/diff/label-list; editors+owners may
  restore and create/delete labels (per §5.2 matrix).

## 4. Non-goals (explicitly out of scope)

- Any frontend rendering — **spec 38**.
- Binary/image file diffing — diffs are **text** only; for non-text docs the API
  returns a "binary, no text diff" marker.
- Real-time streaming of history (polling/REST is sufficient at this phase).
- Changing how history is captured or compacted — **spec 36** owns that.

## 5. Detailed requirements

### 5.1 Data model

One new table; one Alembic migration.

#### 5.1.1 `history_labels`

| Column | Type | Constraints / notes |
| --- | --- | --- |
| `id` | `uuid` | PK, default `gen_random_uuid()` |
| `project_id` | `uuid` | NOT NULL, FK → `projects.id` ON DELETE CASCADE |
| `doc_id` | `uuid` | NULLABLE, FK → `documents.id` ON DELETE CASCADE — NULL for a project-level label |
| `version` | `bigint` | NOT NULL — the doc version (for doc labels) or a project version marker (see §5.4.3) |
| `name` | `text` | NOT NULL, 1–255 chars |
| `created_by` | `uuid` | NULLABLE, FK → `users.id` ON DELETE SET NULL |
| `created_at` | `timestamptz` | NOT NULL default `now()` |

Indexes / constraints:
- Index `ix_history_labels_doc` on `(doc_id, version)`.
- Index `ix_history_labels_project` on `(project_id, created_at)`.
- Unique `uq_history_labels_doc_name` on `(doc_id, name)` `WHERE doc_id IS NOT NULL`.
- Unique `uq_history_labels_project_name` on `(project_id, name)` `WHERE doc_id IS NULL`.

### 5.2 Backend / API

All routes are under the project, JWT-authenticated, and pass through the spec-34
authorisation dependency. Auth matrix:

| Capability | viewer | editor | owner |
| --- | --- | --- | --- |
| list versions / updates | ✅ | ✅ | ✅ |
| get diff | ✅ | ✅ | ✅ |
| list labels | ✅ | ✅ | ✅ |
| create / delete label | ❌ | ✅ | ✅ |
| restore document / project | ❌ | ✅ | ✅ |

Non-members → `404` (do not leak project existence). Member lacking capability → `403`.

Pydantic v2 schemas; responses are JSON. Paths use the project's existing prefix
(e.g. `/api/projects/{project_id}`).

#### 5.2.1 List document versions

`GET /api/projects/{project_id}/docs/{doc_id}/history/versions`

Query params: `before` (version, exclusive; for pagination), `limit` (1–200, default 50).

Response `200`:
```json
{
  "doc_id": "…", "current_version": 142,
  "versions": [
    {"version": 142, "timestamp": "…Z", "author": {"id": "…", "name": "…", "email": "…"} | null,
     "op_count": 3, "size": 1280, "labels": [{"id": "…", "name": "submitted"}]}
  ],
  "has_more": true, "next_before": 92
}
```
- Ordered newest → oldest. Joins author from `users`; `author` is `null` for
  system/agent/unknown. Includes labels attached to each version. Tolerates version
  gaps from compaction (returns only versions that still have a `history_updates` row).

#### 5.2.2 List updates in a range

`GET /api/projects/{project_id}/docs/{doc_id}/history/updates?from={v}&to={v}`

- Returns `history_updates` metadata (no payload bytes) for `from ≤ version ≤ to`,
  ordered ascending. `from`/`to` default to the doc's min/max captured version.
  `400` if `from > to`. Same author-join shape as §5.2.1.

#### 5.2.3 Diff between versions

`GET /api/projects/{project_id}/docs/{doc_id}/history/diff?from={v}&to={v|current}`

- `from` is a captured version. `to` is a captured version **or** the literal
  `current` (diff against the live document's current text).
- The service reconstructs the **text** of each side: it calls
  `reconstruct_state(doc_id, version)` (spec 36) to get the Yjs state, then extracts the
  document's text from the agreed CRDT text type (the shared `Y.Text` / `XmlFragment`
  used by spec 28). For `current`, it reads the live document text.
- Computes a line-then-word diff and returns a structured representation:

Response `200`:
```json
{
  "from": 90, "to": "current", "binary": false,
  "hunks": [
    {"old_start": 12, "old_lines": 3, "new_start": 12, "new_lines": 4,
     "segments": [
       {"type": "context", "value": "\\section{Intro}\n"},
       {"type": "removed", "value": "old line\n"},
       {"type": "added",   "value": "new line\n"},
       {"type": "added",   "value": "extra\n"}
     ]}
  ]
}
```
- `type` ∈ `context | added | removed`. Segment granularity is line-level; within a
  changed region, the service MAY further split into word-level added/removed segments
  (document the choice). Use a well-known diff algorithm implemented in Python (e.g. a
  Myers/`difflib`-based approach written by you) — do not copy Overleaf's diff code.
- If the document is non-text/binary, respond `200` with `{"binary": true, "hunks": []}`.
- `404` if either version is not captured; `400` for malformed params.

#### 5.2.4 Restore a document to a version

`POST /api/projects/{project_id}/docs/{doc_id}/history/restore`

Request:
```json
{"version": 90, "label_name": "restore to v90" }   // label_name optional
```

Restore semantics (CRDT-interoperable, **non-destructive**):
1. Authorise (editor/owner).
2. Reconstruct the target version's **text** via `reconstruct_state` (spec 36).
3. Obtain the **live** document's current authoritative CRDT state from the spec-28
   room (loading/attaching it if no clients are connected).
4. Compute the edit that transforms the current `Y.Text` content into the target text
   (replace-content or a minimal-diff sequence of insert/delete ops on the shared text
   type), and **apply it as a single transaction on the server-side pycrdt document**.
   This produces a normal CRDT update that:
   - is broadcast to all connected clients via the spec-28/29 sync path (so open
     editors converge to the restored text), and
   - is itself captured by spec-36 as a **new** `history_updates` row (a new version) —
     restoring is just another edit, authored by the restoring user.
5. Optionally create a label (`label_name`) on the **new** version produced by the
   restore.
6. Return:
```json
{"doc_id": "…", "restored_from_version": 90, "new_version": 143, "label": {…} | null}
```
- Never deletes or rewrites any `history_*` row. If the live room cannot be reached,
  fail with `409` and change nothing (atomic).
- Concurrency: take the per-doc capture/room lock so the restore update and concurrent
  edits serialise cleanly; the CRDT merge guarantees no corruption, but the restore
  must be applied atomically as one transaction.

#### 5.2.5 Restore a whole project to a label

`POST /api/projects/{project_id}/history/restore`

Request: `{"label_id": "…"}` (must be a project-level label, §5.4.3).

- For each document covered by the project label's snapshot marker, perform a document
  restore (§5.2.4) to that doc's version at the labelled point. Each doc restore is its
  own transaction; the response reports per-doc success/failure:
```json
{"results": [{"doc_id": "…", "status": "restored", "new_version": 50},
             {"doc_id": "…", "status": "skipped", "reason": "no history at label"}]}
```
- Partial failure does not roll back already-restored docs (each is independently
  non-destructive). Returns `200` with the per-doc breakdown, or `404`/`403` for
  auth/label-not-found.

#### 5.2.6 Labels CRUD

- `POST /api/projects/{project_id}/docs/{doc_id}/history/labels` — body
  `{"version": 90, "name": "submitted"}` → `201` with the created label. `409` on
  duplicate name for the doc. editor/owner only.
- `GET  /api/projects/{project_id}/docs/{doc_id}/history/labels` — list labels for a
  doc, newest first. any member.
- `DELETE /api/projects/{project_id}/docs/{doc_id}/history/labels/{label_id}` → `204`.
  editor/owner only. `404` if not found / wrong project.
- `POST /api/projects/{project_id}/history/labels` — project-level label (see §5.4.3).
- `GET  /api/projects/{project_id}/history/labels` — list project-level labels.
- `DELETE /api/projects/{project_id}/history/labels/{label_id}` → `204`.

### 5.3 Frontend / UI

None. (History UI is spec 38.)

### 5.4 Real-time / jobs / integrations

#### 5.4.1 Live-room restore injection

- Provide a service function in the spec-28/29 layer, e.g.
  `async def apply_server_update(doc_id, transaction_fn, author_id)`, that the restore
  service uses to mutate the authoritative pycrdt doc inside a transaction and trigger
  the normal broadcast + persistence + spec-36 capture path. If spec 28 did not already
  expose such a hook, add it here (and note it in the ADR) — it is the only sanctioned
  way to inject a server-originated edit.

#### 5.4.2 Text extraction contract

- Diff and restore both depend on a single agreed "document text" extraction from the
  CRDT state. Reuse the exact shared text type and serialisation that spec 28 defined
  for a LaTeX document. Centralise this in one helper so diff, restore, and spec-36's
  `reconstruct_state` agree byte-for-byte.

#### 5.4.3 Project-level version markers

- A project-level label records, at creation time, the **current `version` of every
  document** in the project as a JSON map persisted alongside the label (store it in a
  new `payload jsonb` column on `history_labels`, NULL for doc labels; add to the
  §5.1.1 migration). Project restore (§5.2.5) reads this map to know each doc's target
  version. Document this in the ADR.

> Update §5.1.1: add column `payload jsonb NULL` to `history_labels` to hold the
> `{doc_id: version}` map for project-level labels. (Keep doc-level labels' `payload`
> NULL.)

### 5.5 Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `HISTORY_DIFF_MAX_BYTES` | `2097152` | Max reconstructed text size (per side) the diff endpoint will process; larger → `413` with `{"binary": false, "too_large": true}` |
| `HISTORY_VERSIONS_PAGE_MAX` | `200` | Upper bound for the `limit` query param on listing |

Read via the spec-02 settings object. No new external services.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach; write your own code.

- `services/project-history/app/js/HttpController.js` and `Router.js` — the shape of the
  history HTTP surface (versions, diff, updates, labels endpoints).
- `services/project-history/app/js/DiffGenerator.js` and `DiffManager.js` — how a diff
  between two versions is produced from a base + updates; informs §5.2.3 (write your own
  text-diff in Python).
- `services/project-history/app/js/LabelsManager.js` — label create/list/delete model;
  informs §5.2.6.
- `services/web/app/src/Features/History/RestoreManager.mjs` — how a restore is turned
  into a normal edit (not a destructive overwrite of history); informs §5.2.4 restore
  semantics.
- `services/web/app/src/Features/History/HistoryController.mjs` and `HistoryRouter.mjs`
  — the web-facing controller/router wiring; informs auth + routing (approach only).

## 7. Acceptance criteria

1. **Given** a doc with captured versions, **when** `GET …/history/versions` is called
   by a member, **then** versions are returned newest-first with author, timestamp,
   op_count, size, and any labels, with working `limit`/`before` pagination and
   `current_version` set correctly.
2. **Given** compaction left gaps in the version sequence, **when** listing versions,
   **then** only versions that still have an update row are returned and pagination
   still terminates correctly.
3. **Given** two captured versions, **when** `GET …/history/diff?from=A&to=B` is called,
   **then** the response contains hunks of `context/added/removed` segments that, when
   applied to A's text, reproduce B's text.
4. **Given** `to=current`, **when** the diff is requested, **then** it diffs the chosen
   version against the live document's current text.
5. **Given** a non-text/binary document, **when** a diff is requested, **then** the
   response is `200` with `{"binary": true, "hunks": []}`.
6. **Given** an editor restores a doc to version V, **when** the restore completes,
   **then** (a) a **new** version N > current is created, (b) the live pycrdt document's
   text equals version V's text, (c) all `history_*` rows for versions ≤ current still
   exist (nothing destroyed), and (d) connected clients receive the restoring update via
   the spec-28/29 sync path.
7. **Given** a restore with `label_name`, **when** it completes, **then** a label with
   that name is attached to the **new** version (N), not to V.
8. **Given** a viewer, **when** they attempt a restore or label create/delete, **then**
   the API responds `403`; **given** a non-member, **then** `404`.
9. **Given** a project-level label capturing `{doc: version}` markers, **when** a project
   restore is requested, **then** each listed doc is restored to its marked version and
   the response reports per-doc status, restoring already-done docs without rollback on a
   later doc's failure.
10. **Given** labels CRUD, **when** creating a duplicate name for the same doc, **then**
    `409`; **when** deleting an existing label, **then** `204` and it disappears from the
    list; cross-project label access returns `404`.
11. **Given** a reconstructed side exceeds `HISTORY_DIFF_MAX_BYTES`, **when** a diff is
    requested, **then** the API responds `413` with `too_large: true` and does no diff work.
12. **Given** the live room is unreachable, **when** a restore is attempted, **then** the
    API responds `409` and no new version or label is created (atomic).

## 8. Test plan

> Keep the suite under 2 minutes. Use a real pycrdt doc in-process for restore tests;
> do not stand up a real WebSocket server — drive the spec-28 service layer directly
> and assert the broadcast hook was invoked (mock the transport).

- **Unit (pytest):**
  - Diff algorithm: hunk/segment generation for inserts, deletes, replacements, and
    "apply A-diff to A reproduces B" property (criterion 3).
  - Text-extraction helper agrees with spec-36 `reconstruct_state` output (criterion contract §5.4.2).
  - Auth matrix mapping role → allowed capability (criteria 8).
  - Diff size guard returns `413` path (criterion 11).
- **Integration (pytest + httpx + test Postgres + fake Redis):**
  - List versions with pagination and gaps (criteria 1, 2).
  - Diff between two versions and version↔current (criteria 3, 4); binary doc (criterion 5).
  - Restore: new version created, live text matches target, history intact, broadcast
    hook called (mocked transport), `label_name` attaches to new version (criteria 6, 7).
  - Restore atomicity when the room hook raises → `409`, no new rows (criterion 12).
  - Labels CRUD incl. duplicate `409`, delete `204`, cross-project `404` (criterion 10).
  - Project-level label + project restore per-doc results (criterion 9).
  - 403/404 access cases across all endpoints (criterion 8).
- **E2E (Playwright):** none at this stage (UI is spec 38).
- **Performance/budget note:** All CRDT work is in-process and synchronous in tests;
  the WebSocket broadcast is mocked. Diffs use small fixtures. No external network.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`; restore/CRDT-injection ADR added under `docs/`.
- [ ] No Overleaf code copied.
