# Spec 12 — File tree model (folders / docs / files) (requirements)

## 1. Summary

This spec adds the **project file tree**: the hierarchy of folders, documents
(`.tex`/text) and files (binary references) inside a project. It defines a single
relational `tree_entities` table with a self-referencing parent, a type enum, a
per-folder unique name constraint, and a service exposing create/rename/move/
delete/list operations with strict path safety. Document **text** (13) and binary
**bytes** (14) attach to entities created here.

## 2. Context & dependencies

- **Depends on:** **11** (`projects` table, ownership rule "404 not 403"),
  **02/03/04/08** (app, async DB, tests, current-user).
- **Unlocks:**
  - **13** — `documents` rows are keyed to a `tree_entities` row of type `doc`.
  - **14** — binary blobs are keyed to a `tree_entities` row of type `file`.
  - **17** — the file-tree UI renders and mutates this model.
  - **21/22** — the compiler reads the tree to assemble the build directory.
- **Affected areas:** backend (model, schemas, service, router, migration), docs (ADR).

## 3. Goals

- One table `tree_entities` representing folders, docs and files (decision &
  justification in §5.1).
- A **root folder** auto-created per project (so every project always has a tree).
- Operations: create folder, create doc, create file-entity, rename, move
  (reparent), delete (recursive for folders), list whole tree.
- **Path safety:** names validated against traversal/separators/control chars;
  names unique (case-insensitively) within a parent folder.
- Cycle prevention on move (a folder cannot be moved into itself or a descendant).
- Alembic migration; full unit + integration tests; suite < 2 min.

## 4. Non-goals (explicitly out of scope)

- Document text content storage and versioning (spec 13).
- Binary bytes / uploads / storage backends (spec 14).
- Duplicate/copy of a subtree, undo, trash/restore of individual entities.
- Frontend tree UI and drag-and-drop (spec 17).
- Linked files / external URLs, symlinks.
- Real-time updates of the tree (later collaboration specs).

## 5. Detailed requirements

### 5.1 Data model

**Decision — single `tree_entities` table (adjacency list), not separate tables.**
Justification:

- **One uniform parent/child mechanism.** Folders, docs and files all live in the
  same hierarchy and share the same operations (rename, move, delete, unique-name).
  A single self-FK table expresses "tree" once instead of three near-duplicate
  schemas plus a polymorphic join.
- **Atomic, simple constraints.** A single `UNIQUE(parent_id, lower(name))`
  enforces per-folder name uniqueness across all entity types in one constraint
  (you cannot have a folder `fig` and a file `fig` siblings).
- **Cheap whole-tree listing.** `SELECT ... WHERE project_id = ?` returns every
  node in one query; the tree is assembled in memory by `parent_id`.
- **Content stays out.** Heavy/variable payloads (doc text in 13, blob refs in 14)
  live in *satellite* tables keyed 1:1 to a `tree_entities` row, keeping this
  table small and the index hot. This avoids Overleaf's monolithic embedded-tree
  document while keeping the model normalised.

Trade-off acknowledged: recursive descent (e.g. delete a folder subtree) needs a
recursive CTE or repeated queries; acceptable at expected project sizes, and we
add a covering index to keep it fast. Record this in
`docs/adr/0012-file-tree-model.md`.

#### Enum `tree_entity_type`

Postgres enum with values: `folder`, `doc`, `file`. (Create via Alembic
`sa.Enum(..., name="tree_entity_type")`.)

#### Table `tree_entities`

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `UUID` | PK, server default `gen_random_uuid()` | Entity id. |
| `project_id` | `UUID` | `NOT NULL`, FK → `projects.id` `ON DELETE CASCADE` | Owning project. |
| `parent_id` | `UUID` | `NULL`, FK → `tree_entities.id` `ON DELETE CASCADE` | Parent folder; `NULL` only for the project root. |
| `type` | `tree_entity_type` | `NOT NULL` | `folder` \| `doc` \| `file`. |
| `name` | `VARCHAR(255)` | `NOT NULL` | Single path segment (see §5.1 path rules). Root's name is `""` (empty) — see below. |
| `is_root` | `BOOLEAN` | `NOT NULL` default `false` | True only for the project root folder. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` default `now()` | |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` default `now()`, `onupdate now()` | Bumped on rename/move. |

**Constraints:**

- `CHECK (type <> 'folder' ⇒ name <> '')` and `CHECK (NOT is_root OR type = 'folder')`
  (root must be a folder). Express as two `CheckConstraint`s.
- `CHECK (is_root = (parent_id IS NULL))` — exactly the root has a null parent;
  every non-root has a parent. (One constraint.)
- **Per-folder unique name, case-insensitive:** a *functional unique index*
  `uq_tree_sibling_name` on `(parent_id, lower(name))`. NULL `parent_id` (the
  single root) is naturally exempt; only one root exists per project anyway.
- Only **folders** may be a `parent_id` target — enforced in the **service**
  layer (DB cannot easily express "parent row's type = folder" without a trigger;
  do it in code and test it). State this explicitly.
- At most **one root per project:** partial unique index
  `uq_tree_one_root_per_project` on `(project_id)` `WHERE is_root`.

**Indexes:**

- PK on `id`.
- `ix_tree_project_id` on `(project_id)` — whole-tree listing.
- `ix_tree_parent_id` on `(parent_id)` — children lookups / recursive descent.
- Functional unique index `uq_tree_sibling_name` (above).
- Partial unique `uq_tree_one_root_per_project` (above).

**Relationships (SQLAlchemy):**

- `TreeEntity.project` → `Project` (many-to-one). Add `Project.tree_entities`
  back-ref (do not eager-load by default; use `lazy="raise"` to force explicit loads).
- `TreeEntity.parent` → self (`remote_side=[id]`); `TreeEntity.children` collection.

**Path model.** A node's path is the `/`-joined chain of ancestor names from (but
excluding) the root down to the node — e.g. `figures/diagram.tex`. Paths are
**derived**, not stored, to avoid update anomalies on move/rename. A helper
`compute_path(entity, parents_by_id)` builds it from an in-memory map. (If a later
spec needs stored paths for performance, add them then.)

**Root creation.** Creating a project (spec 11) does **not** create a tree.
**This spec changes project creation** so that a new project also inserts a single
root `tree_entities` row (`is_root=true`, `type=folder`, `name=""`,
`parent_id=NULL`) in the same transaction. Provide an idempotent
`ensure_root(session, project_id)` for projects created before this spec (none
in practice; include it for safety and migration-data backfill — see Migration).

**Migration:** one Alembic revision that (1) creates the enum, (2) creates the
table with all constraints and indexes, (3) **data-migrates**: inserts a root
folder for every existing project (backfill loop / `INSERT ... SELECT`). Downgrade
drops the table and enum. The migration must be reversible.

### 5.2 Backend / API

Router `app/api/v1/tree.py`, mounted under `/api/v1/projects/{project_id}`. **All
routes require auth** and resolve `project_id` through the spec-11 ownership rule:
if the project is not the caller's (or is soft-deleted / missing), return
**404 project_not_found** before doing anything else. Reuse
`get_owned_project` from spec 11 as a dependency.

**Pydantic schemas (`app/schemas/tree.py`):**

```
TreeEntityType = Literal["folder", "doc", "file"]

CreateEntityIn:
    type: Literal["folder", "doc"]      # "file" entities are created by spec 14's upload, not here
    name: str                           # validated path segment (see rules)
    parent_id: UUID | None = None       # None ⇒ project root

RenameEntityIn:
    name: str

MoveEntityIn:
    new_parent_id: UUID                 # must be a folder in the same project

TreeEntityRead:
    id: UUID
    project_id: UUID
    parent_id: UUID | None
    type: TreeEntityType
    name: str
    is_root: bool
    created_at: datetime
    updated_at: datetime
    path: str                           # derived

TreeNode(TreeEntityRead):
    children: list["TreeNode"] | None   # present (possibly empty) for folders; None for doc/file

TreeRead:
    root: TreeNode                      # nested tree rooted at the project root
```

**Path-segment validation (`app/services/safe_path.py`), reject ⇒ 422:**

- non-empty after `strip()` and ≤ 255 chars (UTF-8);
- contains **no** `/` or `\` (single segment only);
- not `.` or `..`;
- no NUL or other ASCII control chars (`\x00`–`\x1f`, `\x7f`);
- no leading/trailing whitespace or trailing `.`/space (Windows-hostile names);
- not a reserved device name (case-insensitive: `CON`, `PRN`, `AUX`, `NUL`,
  `COM1`–`COM9`, `LPT1`–`LPT9`).

The same validator is reused by specs 13/14. Names are stored **as given**
(after strip) but uniqueness is **case-insensitive** (DB functional index).

#### Endpoints

| # | Method | Path | Auth | Body | Success | Response |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `GET` | `/api/v1/projects/{project_id}/tree` | required | — | `200` | `TreeRead` |
| 2 | `POST` | `/api/v1/projects/{project_id}/tree/entities` | required | `CreateEntityIn` | `201` | `TreeEntityRead` |
| 3 | `PATCH` | `/api/v1/projects/{project_id}/tree/entities/{entity_id}/rename` | required | `RenameEntityIn` | `200` | `TreeEntityRead` |
| 4 | `PATCH` | `/api/v1/projects/{project_id}/tree/entities/{entity_id}/move` | required | `MoveEntityIn` | `200` | `TreeEntityRead` |
| 5 | `DELETE` | `/api/v1/projects/{project_id}/tree/entities/{entity_id}` | required | — | `204` | empty |

**Behaviour details:**

1. **List tree** — single query of all `project_id` rows; assembled in memory into
   `TreeRead.root`. Children of a folder are ordered: folders first, then
   docs/files, each group by `lower(name)` ascending (stable, deterministic).
2. **Create entity** — validates `name`; resolves `parent_id` (default = project
   root); **parent must exist, belong to this project, and be a `folder`** else
   `422`/`404` (see errors). Rejects duplicate sibling name (case-insensitive) →
   `409`. Only `type ∈ {folder, doc}` here (a `doc` creates an empty tree node;
   its text row is created lazily by spec 13 on first save, or here as an empty
   `documents` row once 13 exists — for **this** spec, only the tree node).
3. **Rename** — validates new `name`; rejects renaming the **root** (`409`/`422`);
   rejects a name that collides with an existing sibling → `409`; bumps `updated_at`.
4. **Move** — `new_parent_id` must exist, be in the same project, and be a
   `folder`. Reject moving the **root** (`409`). **Cycle check:** reject if
   `new_parent_id == entity_id` or `new_parent_id` is a descendant of `entity_id`
   → `409 tree_cycle`. Reject if a sibling with the same (case-insensitive) name
   already exists under the new parent → `409 name_conflict`. On success, set
   `parent_id`, bump `updated_at`.
5. **Delete** — recursively deletes the entity and its subtree (relies on
   `ON DELETE CASCADE` self-FK, or an explicit recursive delete; either is fine —
   prefer the DB cascade and assert it). Deleting the **root** is forbidden →
   `409`. Satellite rows (documents/files, once 13/14 exist) cascade via their own
   FKs. Returns `204`.

**Error cases:**

| Condition | Status | `error.code` |
| --- | --- | --- |
| No/invalid token | `401` | `unauthorized` |
| Project missing / not owned / soft-deleted | `404` | `project_not_found` |
| `entity_id` not found in this project | `404` | `entity_not_found` |
| `parent_id`/`new_parent_id` not found in project | `404` | `parent_not_found` |
| Parent target is not a folder | `422` | `parent_not_a_folder` |
| Invalid name (path-safety) | `422` | `invalid_name` |
| Duplicate sibling name | `409` | `name_conflict` |
| Move would create a cycle / move-or-mutate root | `409` | `tree_cycle` / `root_immutable` |
| Bad UUID in path / wrong body type | `422` | `validation_error` |

**Service layer (`app/services/tree_service.py`):**

- `get_tree(session, project_id) -> list[TreeEntity]` (flat) + `build_tree(...)`.
- `create_entity(session, project_id, type, name, parent_id) -> TreeEntity`.
- `rename_entity(session, project_id, entity_id, name) -> TreeEntity`.
- `move_entity(session, project_id, entity_id, new_parent_id) -> TreeEntity`.
- `delete_entity(session, project_id, entity_id) -> None`.
- `is_descendant(session, project_id, ancestor_id, candidate_id) -> bool` (recursive CTE).
- `ensure_root(session, project_id) -> TreeEntity`.

All operations are scoped by `project_id` (never trust an `entity_id` alone:
always `WHERE id = ? AND project_id = ?`).

### 5.3 Frontend / UI

None (spec 17).

### 5.4 Real-time / jobs / external integrations

None.

### 5.5 Configuration

No new env vars. `MAX_TREE_ENTITY_NAME_LENGTH = 255` and reserved-name list are
module constants in `safe_path.py`.

## 6. Overleaf reference (study only — never copy)

> Inkstave uses a flat relational adjacency list; Overleaf nests the tree inside
> the Project document. Study the *rules*, not the storage.

- `services/web/app/src/Features/Project/FolderStructureBuilder.mjs` — how a
  folder hierarchy is assembled; informs `build_tree`.
- `services/web/app/src/Features/Project/ProjectEntityHandler.mjs` — entity
  operations (add/rename/move/delete) and what invariants are kept.
- `services/web/app/src/Features/Project/ProjectLocator.mjs` — how Overleaf finds
  an entity by id/path within the tree and resolves parents; informs our
  `project_id`-scoped lookups and path derivation.
- `services/web/app/src/Features/Project/SafePath.mjs` — **the key reference**:
  filename/path validation rules (forbidden chars, reserved names, length).
  Reimplement equivalent rules in `safe_path.py` independently.
- `services/web/app/src/Features/Project/IterablePath.mjs` — how a path string is
  split/iterated into segments; informs our single-segment validation.

## 7. Acceptance criteria

1. **Given** a freshly created project (via spec 11, now extended), **when** the
   owner `GET`s its tree, **then** they receive a `TreeRead` whose `root` is a
   folder with `is_root=true`, empty `name`, and `children: []`.
2. **Given** the root, **when** the owner creates a folder `figures` and a doc
   `main.tex` under it (root), **then** both appear in the tree with correct
   `type`, `parent_id`, and derived `path` (`figures`, `main.tex`).
3. **Given** a sibling named `Main.tex` already exists, **when** the owner creates
   `main.tex` in the same folder, **then** `409 name_conflict` (case-insensitive).
4. **Given** any of `..`, `a/b`, `a\b`, `con`, a name with a NUL byte, or an
   empty name, **when** used in create/rename/move-target, **then** `422 invalid_name`
   (or the appropriate validation error) and nothing is persisted.
5. **Given** a folder `A` containing folder `B`, **when** the owner moves `A` into
   `B`, **then** `409 tree_cycle` and `A`'s parent is unchanged.
6. **Given** a doc, **when** the owner moves it under a `doc`/`file` entity as the
   new parent, **then** `422 parent_not_a_folder`.
7. **Given** a non-empty folder, **when** the owner deletes it, **then** `204` and
   the folder **and all descendants** are gone from the tree (verified by re-listing).
8. **Given** the project root, **when** the owner tries to rename/move/delete it,
   **then** `409 root_immutable` and the root is unchanged.
9. **Given** user A's project, **when** user B calls any tree endpoint on it,
   **then** `404 project_not_found` (ownership = existence, inherited from 11).
10. The Alembic migration applies and rolls back cleanly, creating the enum,
    table, all constraints and indexes, and backfilling a root for existing
    projects. Suite stays under 2 minutes.

## 8. Test plan

> Fast, DB-only. Use the transactional test DB + async client from spec 04.

- **Unit (pytest):**
  - `safe_path` validator: table-driven cases (valid names; each forbidden class;
    reserved names; length boundary at 255/256; case sensitivity of dedup is at DB
    level so test the index separately).
  - `build_tree`: flat list → nested structure, ordering (folders first, then by
    `lower(name)`), `path` derivation for nested nodes.
  - `is_descendant` / cycle detection with a small hand-built tree.
- **Integration (pytest + httpx + Postgres):**
  - Root auto-creation on project create; `GET /tree` shape.
  - Create folder/doc; nested create; duplicate-name `409` (case-insensitive);
    create under non-folder parent `422`; create under another project's parent `404`.
  - Rename: success, collision `409`, invalid name `422`, root `409`.
  - Move: success (reparent), cycle `409`, non-folder target `422`,
    cross-project target `404`, name collision at destination `409`, root `409`.
  - Delete: leaf and recursive folder delete (subtree gone); root delete `409`.
  - Ownership isolation: user B → `404` on every endpoint.
  - Migration up/down smoke including backfill (one pre-existing project gets a root).
- **E2E (Playwright):** none (UI is spec 17).
- **Performance/budget note:** recursive operations are tested on tiny trees;
  the migration backfill is exercised with a handful of rows. No external I/O.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (model, enum, constraints/indexes,
      service, router, project-create root extension, migration + backfill).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] ADR `docs/adr/0012-file-tree-model.md` justifies the single-table model.
- [ ] No new env vars (or documented in `.env.example`).
- [ ] No Overleaf code copied.
