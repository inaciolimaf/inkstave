# ADR 0012 — File tree as a single adjacency-list table

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 12 — File tree model (folders / docs / files)

## Context

A project contains a hierarchy of folders, documents (`.tex`/text) and files
(binary references). Document text (13) and binary bytes (14) attach to entities
defined here, and the compiler (21/22) walks the tree to assemble a build
directory. Overleaf embeds the whole tree inside the Project document and walks
it; Inkstave needs a relational, queryable model.

## Decision

### One `tree_entities` table (self-referencing adjacency list)

Folders, docs and files all live in **one** table with a `type` enum
(`folder|doc|file`) and a self-FK `parent_id`.

- **One uniform parent/child mechanism.** Rename, move, delete and
  unique-naming are identical across types; a single self-FK expresses "tree"
  once instead of three near-duplicate tables plus a polymorphic join.
- **Atomic per-folder uniqueness.** A single functional unique index
  `uq_tree_sibling_name (parent_id, lower(name))` forbids two siblings sharing a
  name (case-insensitively) across *all* types — you cannot have folder `fig`
  and file `fig` as siblings.
- **Cheap whole-tree listing.** `SELECT … WHERE project_id = ?` returns every
  node in one query; the nested tree is assembled in memory by `parent_id`
  (`ix_tree_project_id` / `ix_tree_parent_id` keep it fast).
- **Content stays out.** Doc text (13) and blob refs (14) live in satellite
  tables keyed 1:1 to a `tree_entities` row, keeping this table small and hot.

**Trade-off:** recursive descent (subtree delete, cycle check) needs a recursive
CTE or `ON DELETE CASCADE`. We use the self-FK **cascade** for subtree delete and
a recursive CTE (`is_descendant`) for the move cycle-check. Acceptable at
expected project sizes.

### Derived paths, not stored

A node's path (`figures/diagram.tex`) is computed from the ancestor chain
(`compute_path`), not stored, to avoid update anomalies on move/rename. If a
later spec needs stored paths for performance, add them then.

### Invariants

- **Root per project.** Project creation (spec 11, now extended) inserts a single
  root folder (`is_root`, `type=folder`, `name=""`, `parent_id=NULL`) in the same
  transaction. A partial unique index `uq_tree_one_root_per_project (project_id)
  WHERE is_root` enforces exactly one; `ensure_root` is idempotent.
- **Check constraints** encode: only a folder may have an empty name; the root
  must be a folder; exactly the root has a NULL parent (`is_root = (parent_id IS
  NULL)`).
- **"Parent must be a folder"** cannot be expressed in the DB without a trigger,
  so it is enforced in the **service** (`_get_entity_as_parent`) and tested.
- **Path safety** (`safe_path.validate_name_segment`, reused by 13/14): single
  segment, no `/`/`\`/traversal/control chars/trailing dot, length ≤ 255, no
  reserved device names — rejections surface as `422 invalid_name`.
- **Ownership = existence** (inherited from spec 11): every route resolves the
  project via `get_owned_project` first → `404 project_not_found` for non-owners.
  Operations are always `project_id`-scoped; an `entity_id` is never trusted
  alone.

### Cascade behaviour

Both FKs are `ON DELETE CASCADE`: deleting a project removes its tree; deleting a
folder removes its subtree (and, later, satellite content rows via their own
FKs). Deleting the **root** is forbidden (`409 root_immutable`).

## Consequences

- New `tree_entity_type` Postgres enum and `tree_entities` table; the migration
  backfills a root for any pre-existing project and drops the enum on downgrade
  (so re-upgrade does not collide).
- `Project.tree_entities` uses `lazy="raise"` to force explicit, N+1-safe loads.
- No new env vars (`MAX_TREE_ENTITY_NAME_LENGTH` + reserved names are constants).

## Alternatives considered

- **Three tables (folders/docs/files) + polymorphic join** — triple the schema
  and a cross-table uniqueness problem; rejected.
- **Embedded tree document (Overleaf-style)** — not queryable relationally, hard
  to index per-folder uniqueness; rejected.
- **Stored materialized paths / `ltree`** — faster ancestor queries but
  update-anomaly-prone on move; deferred until a measured need arises.
