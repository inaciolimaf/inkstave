# Spec 72 — Fix-Pack: Migrations, Health & Tests (requirements)

## 1. Summary

This fix-pack closes **9 confirmed issues** validated by two independent
reviewers across specs 02, 16, 17, 22, 34, 36, and 59. The two most important
items are: (a) the **history compaction job** is missing spec 36 §5.4.2 step 2 —
it never seals the open tail chunk, which can grow unbounded between runs
(issue 142); and (b) the **file-tree keyboard model** is largely untested
(issue 56) and viewer capability-gating of tree mutation controls is missing /
untested (issue 139). The pack also corrects the `/ready` health endpoint to be
Redis-only per spec 02 (issue 6), adds missing CompileRepository unit tests and
a coordinator-test classification note (issues 79, 81), adds a delete-rollback
frontend test (issue 51), strengthens a CodeMirror compartment test (issue 249),
and adds a migration-attribution note for the history XOR constraints (issue 144).

**Severity breakdown (adjusted):** 0 critical, 1 minor that was originally
flagged major (issue 142), and the rest minor/nit. Concretely: 0 critical,
0 major after adjustment, 5 minor, 4 nit. (Issues 56 and 142 carried original
"major" labels and are treated as the highest-priority fixes.)

## 2. Files in scope

Edit **only** these files (the exact payload set). Do not touch anything else.

- `backend/migrations/versions/20260610_0900_c3d5f7a91b24_create_history_tables.py`
- `backend/migrations/versions/20260610_1500_f6a8c2d24e57_history_payload_xor_checks.py`
- `backend/src/inkstave/api/routes/health.py`
- `backend/src/inkstave/history/jobs.py`
- `backend/tests/integration/test_health.py`
- `backend/tests/unit/test_compile_coordinator.py`
- `frontend/src/features/editor/codemirror-editor.test.tsx`
- `frontend/src/features/file-tree/file-tree-panel.test.tsx`
- `frontend/src/features/projects/projects-page.test.tsx`

> **Migrations:** the two migration files above are in scope **only** to add a
> brief attribution comment (issue 144). **Do not change their DDL.** No new
> migration is required by this pack.
>
> **Out-of-scope source note:** issue 139 ideally also gates the file-tree
> mutation controls in `file-tree-panel.tsx`, but that source file is **not in
> this pack's file set**. See issue 139 below for how to handle this within
> scope without reaching outside the set.

## 3. Issues to fix

### Issue 142 — Compaction job missing open-tail seal (spec 36 §5.4.2 step 2)

- **Source spec:** 36-history-capture
- **Severity:** major (original) → minor (adjusted); treat as priority
- **Files:** `backend/src/inkstave/history/jobs.py`

**Problem.** Spec 36 §5.4.2 step 2 requires: "Seal the tail if the open chunk
exceeds `HISTORY_CHUNK_MAX_UPDATES` and was not already sealed by
`ensure_snapshot`." `_compact_doc` only selects **sealed** chunks
(`jobs.py:85-87`, `HistoryChunk.sealed.is_(True)`) and never reads
`settings.history_chunk_max_updates` nor seals the open chunk. The open tail can
grow unbounded between compaction runs if `flush_doc`'s inline sealing did not
fire (e.g. multi-worker / interrupted flush). The numbered spec step is entirely
absent.

**Fix to apply.** In `_compact_doc`, implement step 2:
1. After (or before, matching the spec's ordering) merging sealed chunks, load
   the **open** chunk for the doc (the not-sealed chunk).
2. If its update count `>= settings.history_chunk_max_updates` **and** it is not
   already sealed, **seal it** (and start a new open chunk as the existing
   flush/seal logic does) so it becomes eligible for offload/merge.
3. Keep the rest of the compaction flow intact; do not regress existing behaviour
   for the already-sealed-chunk merge path.

Reuse the existing sealing helper/logic used elsewhere (e.g. in `capture.py`'s
`flush_doc`) rather than duplicating it, if such a helper is reachable from
`jobs.py`. Do not change the inline-seal behaviour in `capture.py` (out of scope);
this is the compaction-side safety net the spec requires.

### Issue 56 — File-tree keyboard model coverage gaps

- **Source spec:** 17-file-tree-ui
- **Severity:** major (original) → minor (adjusted); treat as priority
- **Files:** `frontend/src/features/file-tree/file-tree-panel.test.tsx`

**Problem.** Spec 17 §8/§5.3 require the full keyboard model. The only keyboard
test exercises **only** `ArrowRight` (expand) and `ArrowLeft` (collapse). F2
rename, Enter activation, Delete → confirm dialog, Home/End jump, and type-ahead
(letter keys) are untested.

**Fix to apply.** Add Vitest tests on the tree element firing `keyDown` for:
- **F2** → enters rename mode (rename input/affordance appears).
- **Enter** → activates the focused node (opens the doc / fires the activate
  handler).
- **Delete** → opens the delete confirmation dialog.
- **Home** / **End** → moves focus to the first / last visible node.
- A **letter key** → type-ahead selects the matching node.

Use the component's existing public behaviour and accessible roles/labels; assert
observable outcomes (DOM/dialog/focus), not internals. If a particular
interaction is not implemented in the component, assert the documented behaviour
and, if it genuinely does not exist, report it (do not edit out-of-scope source
to add it).

### Issue 139 — Viewer capability-gated file-tree controls hidden/untested

- **Source spec:** 34-access-control
- **Severity:** nit (original) → minor (adjusted)
- **Files:** `frontend/src/features/file-tree/file-tree-panel.test.tsx`

**Problem.** Spec 34 §8 requires a Vitest test that capability-gated controls are
hidden for viewers (AC10), with a mocked permissions response; §5 requires
viewers see no file-tree mutation actions (create/rename/delete/move). The
panel's mutation gating appears unimplemented (the panel takes no
`canWrite`/`readOnly`/role prop) and is untested.

**Fix to apply.** Add a Vitest test (in `file-tree-panel.test.tsx`) with a
**mocked permissions response** for the **viewer** role asserting that the
file-tree mutation controls (New file/folder, Upload, rename, delete, move) are
**hidden or disabled**.

> **Scope constraint:** the gating logic lives in `file-tree-panel.tsx`, which is
> **not in this pack's file set**. Therefore:
> - If the panel **already** consumes permissions/role (e.g. via a context or
>   hook) and merely lacks a test, add the test asserting the controls are
>   hidden/disabled for viewers — no source edit needed.
> - If the panel does **not** gate at all (no prop/hook), do **not** edit the
>   out-of-scope source here. Write the test to express the required AC10
>   behaviour and mark it appropriately (e.g. `it.todo` / `it.skip` with a clear
>   comment referencing issue 139), and **report** that the gating itself must be
>   implemented in a pack that owns `file-tree-panel.tsx`. This keeps the pack
>   parallel-safe while recording the gap.

### Issue 6 — `/ready` should check Redis only (spec 02)

- **Source spec:** 02-backend-foundation
- **Severity:** minor
- **Files:** `backend/src/inkstave/api/routes/health.py`,
  `backend/tests/integration/test_health.py`

**Problem.** Spec 02 §5.2 / AC3 / AC4 define `/ready` as checking **only Redis**,
returning `{"status":"ready","checks":{"redis":"ok"}}`. The implementation also
checks DB and returns both `redis` and `db`; if `db_engine` is `None` it returns
503 with `db:"error"` even when Redis is up — violating AC3. The test asserts the
expanded `{redis, db}` shape, requiring a real DB and contradicting spec 02's
"no DB yet" scope.

**Fix to apply.**
1. In `health.py`, change the **spec-02 `/ready`** route to check **Redis only**
   and return `{"status":"ready","checks":{"redis":"ok"}}` (503 only when Redis
   is unreachable). **Keep the DB check on the spec-51 `/readyz` route**
   (do not weaken `/readyz`).
2. Update `test_health.py` so the `/ready` test asserts the redis-only shape and
   no longer requires a DB fixture. Ensure the `/readyz` test (if present) still
   asserts the DB+Redis shape.

### Issue 79 — Missing CompileRepository unit tests

- **Source spec:** 22-compile-api-async-jobs
- **Severity:** minor
- **Files:** `backend/tests/unit/test_compile_coordinator.py`

**Problem.** Spec 22 §8 requires "CompileRepository: CRUD, active counts, latest
lookup against the test DB." No dedicated repository tests exist; methods are
covered only indirectly through the coordinator.

**Fix to apply.** Add dedicated `CompileRepository` tests (within
`test_compile_coordinator.py`, since that is the in-scope file) covering, against
the test DB: `create`, `get`, `get_latest`, `get_latest_successful` (if present),
`find_active_for_project`, `count_active_for_project`, and
`count_active_for_user`. Assert each method's contract in isolation (e.g. counts
reflect only active compiles for the given scope; latest lookups return the most
recent row).

### Issue 81 — Coordinator tests classification (integration mark)

- **Source spec:** 22-compile-api-async-jobs
- **Severity:** nit
- **Files:** `backend/tests/unit/test_compile_coordinator.py`

**Problem.** `test_compile_coordinator.py` lives in `tests/unit/` but carries
`pytestmark = pytest.mark.integration` and uses a real DB (`db_session`). Spec 22
§8 calls coordinator debounce/coalesce tests "pure, no HTTP" — they are HTTP-free
but not DB-free.

**Fix to apply.** If the coordinator's debounce/coalesce logic can be exercised
with fakes (no DB), refactor those specific tests to pure unit tests and drop the
`integration` mark for them. If a real DB is genuinely needed (the repository is
intrinsic to the coordinator), **leave the mark** and add a brief comment at the
top of the file explaining why the integration mark and `db_session` are
required, and note it in the relevant ADR if one exists. Do not over-engineer;
the goal is correct classification, not a rewrite.

### Issue 51 — Missing optimistic delete rollback test

- **Source spec:** 16-project-dashboard-ui
- **Severity:** minor
- **Files:** `frontend/src/features/projects/projects-page.test.tsx`

**Problem.** Spec §8 requires an optimistic-update + rollback test; it exists for
rename but **not for delete**. AC §7.8: a failed delete must make the project
reappear and show an error toast. The delete rollback path is untested.

**Fix to apply.** Add a Vitest test "rolls back an optimistic delete when the
request fails": mock the delete mutation to **reject**, trigger a delete, and
assert (a) the deleted project **reappears** in the list and (b) an **error
toast** is requested — mirroring the existing rename-rollback test's structure.

### Issue 249 — CodeMirror compartment test does not assert font-size change

- **Source spec:** 59-user-settings-profile
- **Severity:** nit
- **Files:** `frontend/src/features/editor/codemirror-editor.test.tsx`

**Problem.** The "reconfigures via compartment without recreating the view" test
asserts the `EditorView` DOM node is reused (`after === before`) but never
asserts the font-size actually changed.

**Fix to apply.** After the font-size prop change in that unit test, additionally
assert that the new font size is reflected — prefer asserting the computed
`.cm-content` font-size equals the new value; if jsdom does not surface that
reliably, assert the compartment was reconfigured with the new size (e.g. the
applied theme/extension carries the new `fontSize`). Keep the existing
same-DOM-node assertion.

### Issue 144 — History XOR constraints split across migrations (attribution note)

- **Source spec:** 36-history-capture
- **Severity:** nit
- **Files:**
  `backend/migrations/versions/20260610_0900_c3d5f7a91b24_create_history_tables.py`,
  `backend/migrations/versions/20260610_1500_f6a8c2d24e57_history_payload_xor_checks.py`

**Problem.** Spec 36 §5.1.3's storage-location XOR invariant is enforced by
`CheckConstraint`s added in a **later** migration (`f6a8c2d24e57`, labelled
"spec 40") rather than the initial spec-36 migration. The constraints exist at
head, so this is **not a bug** — but a single spec's invariant is split across
two migrations with a different spec attribution, which is confusing.

**Fix to apply.** This is **documentation/attribution only — no schema change.**
Add a short comment (docstring/header comment) to **both** migration files
clarifying the split:
- In `c3d5f7a91b24` (spec 36): note that the §5.1.3 storage-location XOR check
  constraints were **deferred** to migration `f6a8c2d24e57`.
- In `f6a8c2d24e57`: note that these XOR constraints fulfil spec 36 §5.1.3
  (added under the spec-40 refactor pass), so the attribution is intentional.

**Do not alter the DDL** of either migration. Do not add a new migration; the
constraints already exist at head.

## 4. Acceptance criteria

1. **(Issue 142)** `_compact_doc` loads the open chunk and, when its update count
   `>= settings.history_chunk_max_updates` and it is not already sealed, seals it
   (starting a new open chunk) so step 2 of §5.4.2 is implemented. A test drives
   an oversized open tail through compaction and asserts it gets sealed.
2. **(Issue 56)** Vitest tests cover F2 rename, Enter activation, Delete confirm
   dialog, Home/End, and type-ahead on the file tree.
3. **(Issue 139)** A Vitest test with a mocked viewer-permissions response
   asserts file-tree mutation controls are hidden/disabled for viewers (or, if
   gating is unimplemented in the out-of-scope source, the test records the
   required behaviour as `todo`/`skip` with a comment and the gap is reported).
4. **(Issue 6)** `/ready` returns `{"status":"ready","checks":{"redis":"ok"}}`
   (Redis-only); `/readyz` still checks DB+Redis. `test_health.py` asserts the
   redis-only `/ready` shape with no DB requirement.
5. **(Issue 79)** Dedicated CompileRepository tests cover create/get/get_latest/
   find_active_for_project/count_active_for_project/count_active_for_user against
   the test DB.
6. **(Issue 81)** Coordinator debounce/coalesce tests are either pure (no DB) or
   carry a clear comment justifying the integration mark + `db_session`.
7. **(Issue 51)** A delete-rollback test asserts the project reappears and an
   error toast is requested on a failed delete.
8. **(Issue 249)** The compartment test asserts the new font size is reflected,
   in addition to the reused-DOM-node assertion.
9. **(Issue 144)** Both history migration files carry an attribution comment
   explaining the XOR-constraint split; **no DDL changed**, **no new migration**.
10. All pre-existing tests stay green; the full suite runs in < 2 minutes.

## 5. Test plan

> All tests combined must keep the suite under 2 minutes. No new slow (LaTeX/LLM)
> work is introduced.

- **Backend (pytest):**
  - `history/jobs.py` change covered by a `_compact_doc` test that seeds an open
    chunk above `history_chunk_max_updates` and asserts it is sealed and a new
    open chunk started (add this test to an in-scope test file — if no in-scope
    history test file exists, exercise via the in-scope coordinator/health files
    is not appropriate; instead verify through an existing history compaction
    test if present and **report** if a new test file outside scope would be
    needed). Prefer adding the assertion where history-job tests already live if
    that file is in scope; otherwise report the coverage location.
  - `test_health.py`: assert redis-only `/ready`; keep `/readyz` DB+Redis check.
  - `test_compile_coordinator.py`: add CompileRepository unit tests; adjust
    classification per issue 81.
- **Frontend (Vitest):**
  - `file-tree-panel.test.tsx`: keyboard-model tests (issue 56) + viewer-gated
    controls test (issue 139).
  - `projects-page.test.tsx`: delete-rollback test (issue 51).
  - `codemirror-editor.test.tsx`: font-size-change assertion (issue 249).
- **Migrations:** no test; confirm `alembic upgrade head` / migration import still
  works after the comment-only edits (no DDL change).
- **Performance/budget note:** all additions are fast; run `just test-timed` to
  confirm the suite stays < 2 minutes.

> **Note on issue 142 test location:** if the only natural place for the
> `_compact_doc` test is a history test file **not** in this pack's file set,
> implement the `jobs.py` fix here and **report** that the dedicated compaction
> test must be added by the pack owning that test file, rather than editing an
> out-of-scope file. Do not stretch scope.

## 6. Definition of Done

- [ ] All 9 issues in §3 resolved; none invented, none dropped.
- [ ] Issue 142: `_compact_doc` seals the oversized open tail per §5.4.2 step 2.
- [ ] No released migration DDL changed; no new migration added; issue 144 is a
      comment-only attribution note in both migration files.
- [ ] `/ready` is Redis-only; `/readyz` unchanged.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green (or `todo`/reported where an
      out-of-scope source edit would be required, with the gap reported).
- [ ] No files edited outside §2.
- [ ] Full suite runs in < 2 minutes (`just test-timed`).
- [ ] Lint/format/type-check clean (ruff + pyright on backend; ESLint + tsc on
      frontend).
- [ ] No Overleaf code copied; stack unchanged.
