# Spec 15 — Refactor pass over projects & files (requirements)

## 1. Summary

A refactoring spec covering everything built in **specs 11–14** (project CRUD,
file tree, document content, binary storage). It adds **no features**: it hunts
for bugs, code smells, performance traps (N+1 queries, missing indexes),
path-safety holes and test gaps; evaluates each finding's risk vs. value; applies
the worthwhile fixes; and keeps the suite green and under 2 minutes. It produces a
changelog of changes made and findings deliberately skipped.

## 2. Context & dependencies

- **Depends on:** **11, 12, 13, 14** (all implemented, tests green).
- **Unlocks:** a clean base for the Phase-2 UI specs (16–19) to build on.
- **Affected areas:** backend (projects/files modules, storage, migrations, tests),
  docs (changelog + any updated ADRs).

## 3. Goals

- A systematic review of the spec 11–14 surface area against the checklist in §5.2.
- Worthwhile fixes applied with no external behaviour change (bugs excepted, each
  with a regression test).
- Query-performance sanity: no obvious N+1s on hot paths (tree list, project list,
  document get); indexes present for every filtered/ordered column on hot paths.
- A written record (`docs/refactor/0015-projects-files.md`) of every finding, the
  decision (fixed / skipped), and the reason.

## 4. Non-goals (explicitly out of scope)

- New endpoints, fields, or features.
- API contract changes (response shape, status codes) except documented bug fixes.
- Frontend work (Phase-2 UI is 16–19).
- Cross-cutting concerns owned by later refactor/hardening specs (e.g. global rate
  limiting → 52, observability → 51) unless a concrete bug is found here.
- Large architectural rewrites; prefer targeted, low-risk improvements.

## 5. Detailed requirements

### 5.1 Process

1. **Inventory.** Enumerate the modules from specs 11–14: project model/service/
   router/migration; tree model/service/router/`safe_path`/migration; document
   model/service/router/migration; storage package (interface, local, s3,
   factory)/file model/service/router/migration.
2. **Scan** each against the checklist (§5.2). Use static inspection, run the test
   suite with query logging on the hot paths, and read the SQL emitted for the
   list/tree/get endpoints.
3. **Triage.** For each finding, score **risk** (chance of breaking behaviour) and
   **value** (correctness, security, performance, clarity). Record the decision.
4. **Apply** the worthwhile fixes, smallest-diff-first, running tests after each.
5. **Backfill tests** for any bug fixed and for any uncovered branch found on a
   hot/security path.
6. **Verify** the whole suite is green and < 2 min; write the changelog.

### 5.2 Review checklist (what to look for)

**Correctness / bugs**
- Ownership rule consistently "404 not 403" across *all* project/tree/document/file
  endpoints (no 403 leak, no body leak).
- `project_id` scoping on every entity/document/file lookup (never trust a child id
  alone — always `AND project_id = ?`).
- Transaction boundaries: entity+satellite-row creation atomic; rollback leaves no
  orphan rows or orphan blobs (spec 14 upload failure path).
- Optimistic version check (spec 13) actually prevents lost updates (the
  `WHERE version = base_version` atomic update is in place, not a read-then-write).
- Tree invariants: root immutability, cycle prevention on move, parent-must-be-folder,
  case-insensitive sibling uniqueness — all enforced and not bypassable.
- Blob deletion wired into the spec-12 `file`-entity delete cascade (no orphaned
  blobs when a folder containing files is deleted).

**Performance**
- N+1 queries: tree listing builds from a **single** query (not per-node loads);
  project list does not lazy-load `owner` per row; document/file gets are single
  queries. Fix any `lazy` relationship that fires per-row.
- Indexes: confirm `ix_projects_owner_active` (partial), `ix_tree_project_id`,
  `ix_tree_parent_id`, the functional unique sibling-name index, `ix_documents_project_id`,
  `ix_files_project_id`, and the unique `storage_key` index all exist and are used
  by the hot queries (inspect `EXPLAIN` where cheap). Add any missing index via a
  **new** migration (never edit a released one).
- Recursive operations (delete subtree, `is_descendant`) use a single recursive CTE
  or DB cascade, not Python-side per-node round-trips.
- Streaming: upload/download truly stream (no full-buffer of large files); chunk
  size honoured.

**Security / safety**
- `safe_path` validation applied uniformly (tree create/rename/move target name,
  file upload name); reserved names, traversal, control chars, length all covered.
- Local storage key→path mapping cannot escape the base dir (resolve + containment
  check); S3 keys cannot be influenced by user input beyond ids.
- MIME allow-list and size limit enforced before/while writing, not after.
- No secrets logged; storage credentials never appear in error responses.

**Code quality / smells**
- Duplicated ownership/scoping logic factored into a shared dependency/helper.
- Consistent domain-exception → HTTP-envelope mapping (no raw SQLAlchemy/IntegrityError
  leaking; race-condition on unique constraints translated to the right 409).
- `IntegrityError` on the sibling-name unique index is caught and mapped to
  `409 name_conflict` (race between check-then-insert) — verify or add.
- Dead code, unused params, inconsistent naming, missing type hints.

**Tests**
- Each hot/security path has a regression test. Concurrency/lost-update test
  present (spec 13). Backend-parity test present (spec 14). Migration up/down tests
  present for 11–14.

### 5.3 Backend / API / data model changes

- **Allowed:** internal refactors, new **additive** migrations (e.g. add a missing
  index), broadened exception handling, extracted helpers, added tests.
- **Not allowed:** changing response schemas, status codes, env var names, or table
  columns in a behaviour-visible way; editing already-released migrations.

### 5.4 Real-time / jobs / external integrations

None added.

### 5.5 Configuration

No new env vars. If a default is found to be unsafe (e.g. an overly permissive
MIME fallback), adjusting the default value is permitted and must be noted in the
changelog and `.env.example`.

## 6. Overleaf reference (study only — never copy)

None. This is an inward refactor of Inkstave's own code.

## 7. Acceptance criteria

1. The full test suite passes before and after, and runs in < 2 minutes.
2. **No external behaviour change**: every spec 11–14 acceptance criterion still
   passes unchanged (re-run them). Any intentional change is a bug fix accompanied
   by a new regression test and noted in the changelog.
3. Hot-path query review done: tree-list, project-list and document/file-get each
   issue no N+1 queries (demonstrated via query-count assertions or logged SQL).
4. Every column filtered or ordered on a hot path is backed by an index (verified);
   any added index ships as a new, reversible migration.
5. `safe_path` is provably applied on every name-accepting path (tree + upload);
   a test asserts traversal/reserved/control-char rejection on each.
6. Unique-constraint races (duplicate sibling name) are mapped to `409 name_conflict`,
   not a 500, with a test.
7. A changelog `docs/refactor/0015-projects-files.md` lists each finding, the
   decision (fixed/skipped) and the rationale.
8. Lint/format/type-check clean.

## 8. Test plan

> Reuse the existing fast suite; add targeted regression/perf-sanity tests only.

- **Unit (pytest):** new tests for any bug fixed; broadened `safe_path` cases if
  gaps found; exception-mapping tests (IntegrityError → 409).
- **Integration (pytest + httpx + Postgres):**
  - Query-count assertions (e.g. via a SQLAlchemy event counter fixture) on
    tree-list, project-list, document-get, file-get proving no N+1.
  - Re-assert ownership "404 not 403" across all endpoints in one parametrised test.
  - Orphan checks: failed upload leaves no row/blob; folder-with-files delete
    removes blobs.
  - Concurrency: lost-update test still passes; duplicate-name race → 409.
- **E2E (Playwright):** none (no UI yet).
- **Performance/budget note:** no new slow tests; query-count fixtures are
  in-process. The suite must remain under 2 minutes — measure before finishing.

## 9. Definition of Done

- [ ] Review checklist (§5.2) executed across specs 11–14.
- [ ] Worthwhile fixes applied; no external behaviour change (bugs excepted, each
      with a regression test).
- [ ] All spec 11–14 acceptance criteria still pass; new regression/perf tests green.
- [ ] Any added index ships as a new reversible migration; no released migration edited.
- [ ] Changelog `docs/refactor/0015-projects-files.md` written (fixed vs. skipped).
- [ ] Full suite green and < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] No new features; no Overleaf code copied.
