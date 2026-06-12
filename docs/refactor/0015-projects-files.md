# Refactor 15 — Projects & files (specs 11–14)

Refactoring pass over project CRUD (11), the file tree (12), document content
(13) and binary storage (14). **No features, no external behaviour change** — the
only production edits are clarity smells; everything else is added tests
(regression + perf-sanity) and an audit.

## Method & precondition

- **Pre-refactor:** the full suite (241 tests) was green and under budget.
- Tooling: `pytest --cov` (branch) on the 11–14 modules, extended `ruff`
  (`RUF,SIM,C4,PERF,RET,PIE,B,PTH`), `mypy --strict`, a new **query-count
  fixture** to inspect SQL emitted on the hot paths, and a manual read of the
  scoping/transaction/path-safety code.

The surface was already in good shape (≈97% branch coverage, ownership=404
everywhere, atomic version-checked saves, recursive CTE / DB-cascade for subtree
ops, uniform `safe_path`). Findings were minor smells plus security/perf
**test gaps**.

## Findings catalogue

| id | area | category | decision | rationale / change |
| --- | --- | --- | --- | --- |
| F-001 | `safe_path` | smell | **fixed** | `endswith(".") or endswith(" ")` → `endswith((".", " "))` (ruff SIM). No behaviour change. |
| F-002 | `storage/local` | smell | **fixed** | `try/except FileNotFoundError: pass` → `contextlib.suppress` (ruff SIM105). |
| F-003 | `file_service.upload_file` | smell | **fixed** | Convoluted `(x or None) and x[:255]` → `x[:255] if x else None` (clarity). |
| F-004 | tree create/rename/move | missing-test (security) | **fixed** | The `IntegrityError` → `409 name_conflict` **race** fallbacks (check-then-insert against the unique sibling index) were uncovered. Added three tests that patch the pre-check to miss so the INSERT/UPDATE races into the unique index → 409, never 500 (AC6). |
| F-005 | tree-list / project-list / document-get / file-get | perf (N+1) | **verified + test** | No N+1 found: the whole tree comes from one query (assembled in memory), project-list never lazy-loads `owner`, document-get and file-get are each a bounded couple of queries. Added **query-count assertions** proving the statement count does not scale with row count (AC3). |
| F-006 | `file_service.get_file` | missing-test | **fixed** | The "file entity without a `files` row → 404" edge was uncovered; added a test (a `file` entity created without an upload). |
| F-007 | `storage/base.ObjectStore.get` | missing-test | **fixed** | The base-class `get` convenience was uncovered; added a test. |
| F-008 | `file_service.sniff_content_type` | missing-test | **fixed** | The WebP branch + declared/octet fallbacks were partly uncovered; added a table-driven sniff test. |
| F-009 | `storage/s3` credential branches | missing-test | **fixed** | Constructing `S3ObjectStore` with endpoint/credentials + a faked round-trip now covered. |
| F-010 | ownership across resources | test (security) | **fixed** | Added a consolidated parametrised test asserting `404 project_not_found` for a non-owner across project/tree/document/file GETs (AC2 re-assert). |
| F-011 | indexes on hot paths | perf | **verified, no change** | All filtered/ordered columns are indexed: `ix_projects_owner_active` (partial, `owner_id, updated_at DESC`), `ix_tree_project_id`, `ix_tree_parent_id`, the functional unique `uq_tree_sibling_name`, `ix_documents_project_id`, `ix_files_project_id`, `uq_files_storage_key`. No new migration needed. |
| F-012 | `tree._read` single-entity path | perf | **skipped** | Building a create/rename/move response loads the whole project tree to derive one node's `path` (O(n) on an infrequent path). Correct; optimising would add risk for little value vs. the hot list path. Deferred. |
| F-013 | `ALLOWED_UPLOAD_MIME` default | security | **verified, no change** | The default allow-list excludes `application/octet-stream` (per spec 14) — already the safe default. No change. |
| F-014 | secrets in logs/errors | security | **verified, no change** | Grep + read: no secrets/credentials logged; storage `ClientError`s surface as a generic 500 (traceback logged, not returned). |

## §5.2 review summary

- **Correctness:** ownership=404 everywhere; `project_id`-scoped lookups
  throughout; upload failure rolls back the entity **and** best-effort-deletes
  the blob (no orphans); the version check is the atomic `WHERE version = ?`
  update; root immutability / cycle-prevention / parent-must-be-folder /
  case-insensitive uniqueness all enforced; folder-with-files delete removes
  blobs via the spec-12 cascade wired to the store.
- **Performance:** no N+1 on the hot paths (now test-guarded); all hot-path
  columns indexed; recursive ops use a CTE / DB cascade.
- **Security:** `safe_path` applied on every name-accepting path (tree
  create/rename, file upload); local key→path containment-checked; MIME/size
  enforced while streaming.

## Behaviour unchanged — verification

- All 241 pre-existing tests still pass **unmodified**; +17 new tests (258 total).
- The three production edits (F-001/2/3) are pure clarity refactors with
  identical behaviour. No response shape, status code, env var, or column
  changed; no released migration edited; no new migration needed.

## Measurements

| Metric | Before | After |
| --- | --- | --- |
| Backend tests | 241 | 258 |
| Backend branch coverage | ~97% | ~98% (`file_service`, `storage/base` → 100%) |
| Suite wall-clock | well under budget | ~14 s (no slow tests added) |
| `ruff` / `mypy --strict` | clean | clean |
