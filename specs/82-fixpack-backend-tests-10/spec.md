# Spec 82 — Fix-pack: tree move coverage, blob cleanup, e2e & budget (batch 10) (requirements)

## 1. Summary

This fix-pack applies **9 confirmed issues** validated by two independent
reviewers. They cover missing file-tree **move** integration coverage
(cross-project parent, destination name-collision, ownership-isolation sweep), the
tree-delete → blob-cleanup chain, the sparse e2e `@full` tier and its worker
default, the perf-gate CLI exit-code test, a missing ADR, and the suite-wide
under-2-minute budget regression.

Severity breakdown (adjusted severity):
- **major:** 0
- **minor:** 5 (IDs 32, 33, 43, 229, 83)
- **nit:** 4 (IDs 36, 230, 173, 226)

Source specs touched: `12-file-tree-model`, `14-binary-file-storage`,
`22-compile-api-async-jobs`, `42-agent-tools`, `53-performance-test-speed`,
`54-e2e-suite`.

## 2. Files in scope

Edit **only** these files (exact payload set). Do not modify anything outside
this list — other fix-packs run in parallel on disjoint files.

- `backend/src/inkstave/services/tree_service.py`
- `backend/tests/integration/test_tree_api.py`
- `backend/tests/unit/test_performance.py`
- `docs/adr/` (add a new ADR file here for Issue 173)
- `frontend/e2e/full.spec.ts`
- `frontend/e2e/support/env.ts`
- `frontend/playwright.config.ts`

> Restrict-edits note: Issue 83 (suite budget) is a project-level pytest
> invocation concern. The pytest config file (e.g. `pyproject.toml`/`pytest.ini`/
> CI workflow) is **not** in this pack's file set. Apply the budget fix **only** if
> it can be expressed within the in-scope files; otherwise document the required
> change (add `-n auto`) in the §3 Issue 83 notes and the ADR, and do not edit
> out-of-scope config. See Issue 83 for the exact handling.

## 3. Issues to fix

### Issue 32 — move to a cross-project parent untested (→ 404)
- **Source spec:** 12-file-tree-model
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_tree_api.py`
- **Problem:** Spec 12 §8 requires "Move: cross-project target → 404." No test moves
  an entity where `new_parent_id` belongs to a **different** project. The service
  (`tree_service._get_entity_as_parent`, lines ~253-263) uses a project-scoped query
  that raises `ParentNotFoundError` (404) for a cross-project parent, but coverage is
  absent (the existing cross-project test is a CREATE, not a MOVE).
- **Fix to apply:** Add an integration test that creates a folder in a **second**
  project and PATCHes `.../entities/{id}/move` on an entity in the first project with
  `new_parent_id` pointing at the second project's folder, asserting `404`
  `parent_not_found`. Follow the existing move-test setup style.

### Issue 33 — move name-collision at destination untested (→ 409)
- **Source spec:** 12-file-tree-model
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_tree_api.py`
- **Problem:** Spec 12 §8 requires "name collision at destination 409" for move. No
  test moves an entity into a folder that already contains a same-named sibling. The
  service (`tree_service.move_entity`, line ~298, `_sibling_exists` →
  `NameConflictError`) handles it, but it is untested.
- **Fix to apply:** Add an integration test that creates two entities with the **same
  name** in different folders, then PATCHes `.../move` to move one into the other's
  folder, asserting `409` `name_conflict`.

### Issue 36 — move endpoint omitted from ownership-isolation sweep
- **Source spec:** 12-file-tree-model
- **Severity:** nit
- **File(s):** `backend/tests/integration/test_tree_api.py`
- **Problem:** `test_ownership_isolation` (lines ~272-281) sweeps GET tree, POST
  create, PATCH rename, DELETE — but omits the PATCH **move** endpoint. Spec 12 §7
  AC9 says "any tree endpoint" must return 404 `project_not_found` for user B.
- **Fix to apply:** Add a user-B `PATCH .../entities/{id}/move` call to the
  ownership-isolation `calls` list and assert `404` `project_not_found`, matching the
  existing sweep entries.

### Issue 43 — tree-delete → blob-cleanup chain untested
- **Source spec:** 14-binary-file-storage
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_tree_api.py`,
  `backend/src/inkstave/services/tree_service.py`
- **Problem:** Spec 14 §9 DoD requires "Spec-12 `file`-entity delete path wired to
  delete the blob (no orphan)." The wiring exists (`tree_service.delete_entity` +
  `_file_keys_in_subtree` + best-effort `store.delete`, lines ~330-349; the tree
  route passes `store`), but no integration test exercises the tree-API
  `DELETE /tree/entities/{id}` path on an entity that has a blob and verifies the
  blob is removed. The only blob-delete test lives in `test_files_api.py` and uses
  the files API endpoint.
- **Fix to apply:** Add a `test_tree_api.py` case that uploads/creates a file blob,
  deletes the entity via the tree-API `DELETE /tree/entities/{id}` using an
  in-memory `ObjectStore`, and asserts the blob key is gone afterward. The
  `tree_service.py` entry is in scope **only** if a tiny adjustment is needed to make
  the delete-cascade testable (e.g. ensuring the store dependency is injectable in
  the test); prefer leaving `tree_service.py` unchanged if the existing wiring is
  already testable via the route + in-memory store fixture.

### Issue 230 — e2e workers default deviates from spec (cores vs 2)
- **Source spec:** 54-e2e-suite
- **Severity:** nit
- **File(s):** `frontend/playwright.config.ts`, `frontend/e2e/support/env.ts`
- **Problem:** Spec 54 §5.5 says `E2E_PLAYWRIGHT_WORKERS` defaults to "from cores."
  The implementation caps workers at 2 by default (`workers: e2e.workers ?? 2`) to
  avoid saturating the single shared backend — a sensible, comment-documented
  constraint that diverges from the stated default.
- **Fix to apply:** Keep the default-2 cap (it is the correct engineering choice for
  the shared single backend). Since the spec file is out of scope, make the
  divergence explicit in code: ensure the existing rationale comment in
  `playwright.config.ts` (and the `env.ts` parsing/default for
  `E2E_PLAYWRIGHT_WORKERS`) clearly documents that the default is intentionally **2**
  (not "from cores") and why. Confirm `E2E_PLAYWRIGHT_WORKERS` still overrides it.

### Issue 229 — sparse e2e @full tier
- **Source spec:** 54-e2e-suite
- **Severity:** minor
- **File(s):** `frontend/e2e/full.spec.ts`, `frontend/playwright.config.ts`
- **Problem:** Spec 54 §8 lists four `@full` additions: (1) real Tectonic one-page
  compile, (2) multi-hunk partial accept/reject of the agent diff, (3)
  viewer/permission edge cases, (4) an additional browser engine. `full.spec.ts`
  contains only one test (agent diff **reject** path — part of item 2). The `full`
  Playwright project also reuses Desktop Chrome (same engine as smoke).
- **Fix to apply:** Extend `full.spec.ts` with `@full` tests for the missing items:
  (1) a real-Tectonic (`COMPILE_MODE=real`) one-page compile producing a PDF; (2) a
  **multi-hunk partial accept** of an agent diff (complementing the existing reject
  test); (3) viewer/permission edge cases (e.g. a viewer cannot edit/compile where
  not permitted). In `playwright.config.ts`, configure the `full` project (or add a
  separate project) to run on an additional engine (Firefox or WebKit) so item 4 is
  covered. Keep these tests opt-in/nightly (gated by the `@full` grep) so the
  default smoke run stays fast and within budget.

### Issue 83 — backend suite exceeds the 2-minute budget
- **Source spec:** 22-compile-api-async-jobs
- **Severity:** minor
- **File(s):** (none in payload — project-level pytest invocation)
- **Problem:** The full backend suite takes ~3m01s single-threaded (baseline: 759
  passed, 1 skipped), violating the DoD "Full suite runs in < 2 minutes." This is a
  suite-wide issue, not spec-22's tests (which are fast in isolation). The defect is
  the missing `-n auto` in the default/CI pytest path.
- **Fix to apply:** Restore the budget by enabling parallel test execution (add
  `-n auto`, via `pytest-xdist`) to the default/CI pytest invocation. The pytest
  config (`pyproject.toml`/`pytest.ini`) and CI workflow are **out of this pack's
  file set**; therefore record the required change as an ADR (see Issue 173 — the new
  ADR may also cover this budget decision) and, if the implementing harness permits a
  config edit, apply `-n auto` there. If config edits are not permitted by the scope
  guard, the deliverable for this issue is the documented decision (ADR + DoD note)
  plus verification that the suite under `-n auto` completes in < 2 minutes. Do not
  edit files outside §2.

### Issue 173 — missing ADR for spec 42
- **Source spec:** 42-agent-tools
- **Severity:** nit
- **File(s):** `docs/adr/`
- **Problem:** `specs/42-agent-tools/README.md` step 7 says to add a short ADR for
  notable design choices (e.g. the section-locator heuristic). No ADR 0042 exists;
  the ADR sequence jumps 0041 → 0043, despite notable choices (module-level services
  vs injected service objects; `@dataclass` vs `BaseModel` for `ToolContext`).
- **Fix to apply:** Add `docs/adr/0042-agent-tools.md` (matching the existing ADR
  format/numbering) recording the spec-42 design decisions: the section-locator
  heuristic, module-level services vs injected service objects, and `@dataclass`
  `ToolContext` vs `BaseModel`. Keep it short, in the established ADR style. (If
  Issue 83's `-n auto`/budget decision needs a home, this ADR or a separate
  `docs/adr/` file may record it.)

### Issue 226 — perf-gate CLI exit-code not tested
- **Source spec:** 53-performance-test-speed
- **Severity:** nit
- **File(s):** `backend/tests/unit/test_performance.py`
- **Problem:** Spec 53 §8 requires "a small unit test of the timing-gate script:
  given a test-timing.json over budget it exits non-zero; under budget, zero." The
  existing tests call `gate.evaluate(...)` and assert `result.ok`/`result.messages`
  but never invoke the `main()` CLI entrypoint nor verify the POSIX exit code.
- **Fix to apply:** Add tests that exercise the gate's `main()` entrypoint
  (`check_test_budget.main([...])`): one with an **over-budget** timing JSON asserting
  the return/exit code is `1` (non-zero), and one with an **under-budget** JSON
  asserting `0`. Write the temporary timing JSON to a tmp path fixture, or run the
  script as a subprocess and check `returncode`. Match the existing test style in
  `test_performance.py`.

## 4. Acceptance criteria

1. **(Issue 32)** An integration test PATCHes move with a cross-project
   `new_parent_id` and asserts `404` `parent_not_found`; it passes.
2. **(Issue 33)** An integration test moves an entity into a folder with a same-named
   sibling and asserts `409` `name_conflict`; it passes.
3. **(Issue 36)** The ownership-isolation sweep includes a user-B PATCH `.../move`
   call asserting `404` `project_not_found`; it passes.
4. **(Issue 43)** An integration test deletes a file entity via the tree-API DELETE
   route with an in-memory ObjectStore and asserts the blob key is removed; it
   passes.
5. **(Issue 230)** `playwright.config.ts`/`env.ts` clearly document the intentional
   default of 2 workers, and `E2E_PLAYWRIGHT_WORKERS` still overrides it.
6. **(Issue 229)** `full.spec.ts` contains `@full` tests for a real-Tectonic one-page
   compile, multi-hunk partial accept, and viewer/permission edge cases; the `full`
   project (or a sibling project) runs on an additional browser engine.
7. **(Issue 83)** The backend suite runs in < 2 minutes (under `-n auto`), and the
   decision/change is recorded (ADR + DoD note); no out-of-scope file edited without
   permission.
8. **(Issue 173)** `docs/adr/0042-agent-tools.md` exists in the established ADR style
   recording the spec-42 decisions.
9. **(Issue 226)** Unit tests invoke the perf-gate `main()` and assert exit code `1`
   over budget and `0` under budget; they pass.

## 5. Test plan

> All project tests combined must keep the suite under 2 minutes. The `@full` e2e
> tests are opt-in/nightly (gated by the `@full` grep) and the real-Tectonic compile
> is only exercised there — they must not run in the default smoke/CI fast path.

- **Existing green:** Run the backend pytest tree/performance suites and the e2e
  smoke tier before/after; all previously-passing tests must stay green.
- **New/updated backend tests (pytest + httpx / test DB / in-memory store):**
  - Move cross-project 404 (Issue 32), move name-collision 409 (Issue 33),
    ownership-isolation move 404 (Issue 36), tree-delete blob-cleanup (Issue 43) in
    `test_tree_api.py`.
  - Perf-gate `main()` exit-code tests (Issue 226) in `test_performance.py`.
- **New/updated e2e tests (Playwright):** `@full`-tagged real-Tectonic compile,
  multi-hunk partial accept, and viewer/permission edge cases in `full.spec.ts`;
  additional-engine project config in `playwright.config.ts` (Issue 229). These are
  opt-in/nightly only.
- **Budget (Issue 83):** Enable `-n auto` (pytest-xdist) on the default/CI run and
  re-measure: the backend suite must complete in < 2 minutes. Record the decision in
  the new ADR.
- **Performance/budget note:** Default fast suite stays under 2 minutes; the
  `@full`/real-Tectonic work is excluded from it via the `@full` grep gate.

## 6. Definition of Done

- [ ] All 9 issues in §3 fixed exactly as described (Issue 83 applied or its decision
      documented per the scope guard).
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; previously-green tests stay
      green; the default backend suite runs in < 2 minutes.
- [ ] Only files listed in §2 were modified (plus the documented Issue 83 decision).
- [ ] `docs/adr/0042-agent-tools.md` added.
- [ ] Lint/format/type-check clean (ruff + pyright/mypy backend; ESLint + Prettier
      + tsc frontend).
- [ ] No unrelated refactors; no Overleaf code copied.
