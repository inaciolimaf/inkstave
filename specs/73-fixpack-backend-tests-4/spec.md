# Spec 73 — Fix-Pack: Backend & Tests 4 (requirements)

## 1. Summary

This fix-pack closes **10 confirmed issues** validated by two independent
reviewers across specs 03, 17, 18, 28, 30, 38, and 42. The work is mostly
test-coverage and type-contract hardening for the realtime collab core
(manager-level compaction trigger, reordered-update convergence, deterministic
waits, a missing return type, a duplicate/uncovered race), plus a `Ping` model
roundtrip assertion, two frontend type-contract alignments (`ProjectTree`,
`DocumentContent.name`), a history-timeline focusability test, and an optional
`size` field on the agent `list_tree` tool output.

**Severity breakdown (adjusted):** 0 critical, 0 major, 5 minor, 5 nit.

## 2. Files in scope

Edit **only** these files (the exact payload set). Do not touch anything else.

- `backend/src/inkstave/agent/tools/list_tree.py`
- `backend/tests/integration/test_collab_manager.py`
- `backend/tests/integration/test_collab_refactor.py`
- `backend/tests/integration/test_collab_ws_refactor.py`
- `backend/tests/integration/test_db_session.py`
- `frontend/src/features/editor/api.ts`
- `frontend/src/features/editor/types.ts`
- `frontend/src/features/file-tree/types.ts`
- `frontend/src/features/history/HistoryTimeline.test.tsx`

> If a fix appears to require a file outside this list, **stop and report**.
> Notably, `backend/src/inkstave/collab/manager.py` and the backend document
> content schema (`schemas/document.py` / `documents.py`) are **out of scope** —
> for issue 64, prefer the frontend-only alignment unless the spec note below
> says otherwise.

## 3. Issues to fix

### Issue 105 — Manager-level inline compaction trigger untested

- **Source spec:** 28-crdt-backend-pycrdt
- **Severity:** minor
- **Files:** `backend/tests/integration/test_collab_manager.py`

**Problem.** Spec 28 §5.2.5 requires that after `COLLAB_SNAPSHOT_EVERY_UPDATES`
updates, `handle_update` → `_maybe_compact` → `_compact` fires. All manager tests
use the default `snapshot_every_updates=200`, so the count-based trigger is never
exercised at the manager layer (`test_collab_manager.py:78`).

**Fix to apply.** Add a test instantiating the manager with a **small**
`snapshot_every_updates` (e.g. 1 or 2), send enough updates through
`handle_update`, and assert `_compact` fired — e.g. by asserting a snapshot row
was written, or by spying on `_compact`. Use the existing manager fixtures and
override mechanism (`over.get('snapshot_every_updates', ...)`).

### Issue 113 — Replace fixed sleeps with deterministic polling

- **Source spec:** 30-refactor-realtime-core
- **Severity:** minor
- **Files:** `backend/tests/integration/test_collab_refactor.py`,
  `backend/tests/integration/test_collab_ws_refactor.py`

**Problem.** Several tests use fixed `asyncio.sleep` instead of deterministic
synchronisation. `test_reconnect_resyncs_and_converges` and
`test_connect_disconnect_cycles_leave_no_leak` use `sleep(0.05)` (ws_refactor:50,
80, 89) to wait for a **positive** condition; a `_poll` helper already exists but
is barely used. `test_no_eviction_while_connections_remain` (refactor:111) sleeps
0.1 s for a **negative** (non-eviction) assertion.

**Fix to apply.**
1. Replace the **positive-condition** `sleep(0.05)` calls in
   `test_collab_ws_refactor.py` (lines ~50, ~80, ~89) with `_poll` on the
   expected state (e.g. poll until the update is processed / the doc converged /
   the leak count returns to the expected value).
2. Keep a **single bounded sleep** only for the genuine **non-eviction negative
   assertion** in `test_collab_refactor.py:111` (you cannot poll for "something
   that should never happen") — leave that intact (optionally with a clarifying
   comment).

### Issue 114 — Convergence under reordered updates untested at manager level

- **Source spec:** 30-refactor-realtime-core
- **Severity:** minor
- **Files:** `backend/tests/integration/test_collab_refactor.py`

**Problem.** AC4 requires a deterministic convergence test for reordered/concurrent
updates. Coverage exists only at the bare `YDocument` level
(`test_collab_ydocument.py::test_concurrent_inserts_commute`); no manager- or
integration-level test exercises reordered delivery through
`DocumentManager.handle_update`.

**Fix to apply.** Add a manager-/integration-level test that delivers updates in
a **reordered** sequence through `DocumentManager.handle_update` and asserts the
document **converges** to the same final state regardless of order (e.g. apply
the same set of updates in two different orders to two docs and assert equal
final content/state vector).

### Issue 116 — Missing return type on `_setup` helper

- **Source spec:** 30-refactor-realtime-core
- **Severity:** nit
- **Files:** `backend/tests/integration/test_collab_ws_refactor.py`

**Problem.** `async def _setup(db_session: AsyncSession):` (line ~24) lacks a
return type annotation. mypy is `strict` but only checks `src/`, so it is not
caught; it is inconsistent with other helpers.

**Fix to apply.** Add an explicit return type annotation to `_setup` (e.g.
`-> tuple[...]` matching what it actually returns). Keep the body unchanged.

### Issue 115 — Duplicate test + uncovered F-001 swap race

- **Source spec:** 30-refactor-realtime-core
- **Severity:** nit
- **Files:** `backend/tests/integration/test_collab_refactor.py`,
  `backend/tests/integration/test_collab_manager.py`

**Problem.** `test_concurrent_acquire_loads_once` appears in **both** files with
effectively identical bodies, and neither injects a **concurrent eviction** to
drive the lock-identity-swap retry path (`manager.py:123` —
`if self._locks.get(document_id) is not lock: continue`). So the F-001 swap path
is duplicated, not regression-tested.

**Fix to apply.** In `test_collab_refactor.py` (the spec-30 file), replace or
augment the duplicate so it **specifically** exercises the F-001 swap path: force
eviction (e.g. `idle_evict_seconds=0`) to fire **concurrently** with two acquires
via a coordinating barrier/event, and assert the lock-identity-mismatch retry
still loads the document **exactly once**. Leave the spec-28 copy in
`test_collab_manager.py` as the original (or de-duplicate by keeping one
meaningful version) — do not delete coverage; the net result must be one
genuine swap-race regression test plus no accidental loss of the load-once
assertion.

### Issue 9 — Ping model roundtrip: timestamps + updated_at bump

- **Source spec:** 03-database-foundation
- **Severity:** minor
- **Files:** `backend/tests/integration/test_db_session.py`

**Problem.** AC7/§8 require: insert and read a `Ping`, assert UUID + timestamps +
`updated_at` bump. `test_factory_creates_distinct_persisted_pings` only asserts
`isinstance(id, uuid.UUID)` and distinct notes/ids; it does not assert
`created_at`/`updated_at` are non-None and timezone-aware after a DB roundtrip,
nor that updating the note bumps `updated_at`.

**Fix to apply.** Extend the test (or add a focused one) to:
1. After a DB roundtrip, assert `created_at` and `updated_at` are **non-None**
   and **timezone-aware** datetimes.
2. Update the `note`, flush, and assert `updated_at` **strictly advances**
   (new `updated_at` > old `updated_at`).

### Issue 60 — Missing `ProjectTree` interface (spec 17 §5.1)

- **Source spec:** 17-file-tree-ui
- **Severity:** minor
- **Files:** `frontend/src/features/file-tree/types.ts`

**Problem.** Spec 17 §5.1 defines `ProjectTree` (`{ rootId; entities: TreeEntity[] }`)
as the normalised flat-map shape. The implementation has `TreeEntity`, `TreeNode`,
`FlatNode` but **no** `ProjectTree`, working directly off the nested `TreeNode`.

**Fix to apply.** Add the `ProjectTree` interface
(`{ rootId: string; entities: TreeEntity[] }`) to `types.ts` so the stated data
model is represented. The minimal, lowest-risk fix is to **declare the interface**
matching §5.1 (and optionally a small helper/derivation if trivial); do not
rewire the whole UI normalisation. If you choose not to adopt it in the data flow,
declaring the interface to match the spec contract satisfies the fix; note the
chosen normalisation form in a code comment.

### Issue 155 — HistoryTimeline focusability assertion missing (AC10)

- **Source spec:** 38-history-ui
- **Severity:** nit
- **Files:** `frontend/src/features/history/HistoryTimeline.test.tsx`

**Problem.** Spec 38 §8 requires focusability assertions (criterion 10).
`HistoryTimeline.tsx:34` sets `tabIndex={0}` with an `onKeyDown`, but there is no
test asserting version rows are keyboard-reachable.

**Fix to apply.** Add a Vitest test asserting version rows have `tabIndex=0` and
respond to keyboard activation (Enter/Space) — e.g. `userEvent.tab()` reaches a
row and `userEvent.keyboard('{Enter}')`/`{ }` triggers the row's activation
handler. Assert observable behaviour (focus + activation), not internals.

### Issue 64 — `DocumentContent.name` field missing (spec 18 §5.1)

- **Source spec:** 18-editor-ui-codemirror
- **Severity:** minor
- **Files:** `frontend/src/features/editor/types.ts`,
  `frontend/src/features/editor/api.ts`

**Problem.** Spec 18 §5.1 declares `DocumentContent { id; name; content; version }`.
The implementation omits `name` (`types.ts:4-8`); `api.ts` maps only
`entity_id`/`content`/`version`. The name is sourced from `TreeEntity`, so the UI
works, but the type contract deviates from §5.1.

**Fix to apply.** Align the frontend type contract with §5.1:
1. Add `name: string` to the `DocumentContent` interface in `types.ts`.
2. In `api.ts`, map `name` from the wire response into `DocumentContent`.

> **Scope note:** the backend `DocumentContentRead` schema also omits `name`, but
> that file is **out of scope** for this pack. If the wire response does **not**
> currently include `name`, do **not** edit the backend here. Instead, source
> `name` on the frontend from the data already available (e.g. pass through the
> tree entity name when constructing `DocumentContent`, or make `name` optional
> if no value is available) so the **frontend type contract matches §5.1** without
> reaching outside scope, and **report** that the backend wire should add `name`
> in the pack that owns the document schema. Do not break existing callers.

### Issue 169 — `list_tree` output missing optional `size` field

- **Source spec:** 42-agent-tools
- **Severity:** nit
- **Files:** `backend/src/inkstave/agent/tools/list_tree.py`

**Problem.** Spec 42 §5.2.5 output schema is
`{node_id, path, type: folder|doc|file, size?, is_binary?}`. `list_tree.py:54-61`
appends only `node_id`, `path`, `type`, `is_binary` — `size` is omitted. (`size`
is explicitly **optional**, so this is a contract-completeness nit, not a
violation.)

**Fix to apply.** Include an optional `size` field for `doc`/`file` nodes,
sourcing it from the available size data (e.g. `file.size_bytes` /
`document.size_bytes`). Join/select the size as needed within `list_tree.py`'s
existing query and add `size` to the emitted node dict for doc/file entries
(omit or null for folders, per the optional contract). Keep the change minimal
and the existing fields unchanged.

## 4. Acceptance criteria

1. **(Issue 105)** A manager test with a small `snapshot_every_updates` sends
   updates and asserts `_compact` fired (snapshot row / spy).
2. **(Issue 113)** The positive-condition `sleep(0.05)` calls in
   `test_collab_ws_refactor.py` are replaced with `_poll`; only the genuine
   non-eviction negative check retains a bounded sleep.
3. **(Issue 114)** A manager-/integration-level test delivers reordered updates
   through `handle_update` and asserts convergence.
4. **(Issue 116)** `_setup` has an explicit return type annotation.
5. **(Issue 115)** A test forces concurrent eviction during acquire (via a
   barrier) and asserts the lock-identity-mismatch retry loads exactly once; no
   load-once coverage is lost.
6. **(Issue 9)** The Ping test asserts tz-aware `created_at`/`updated_at` after a
   roundtrip and that `updated_at` strictly advances on note update.
7. **(Issue 60)** `ProjectTree { rootId; entities: TreeEntity[] }` exists in
   `file-tree/types.ts`.
8. **(Issue 155)** A HistoryTimeline test asserts version rows are focusable
   (`tabIndex=0`) and respond to Enter/Space.
9. **(Issue 64)** `DocumentContent` includes `name` and `api.ts` populates it
   (frontend-sourced if the backend wire lacks it; backend gap reported).
10. **(Issue 169)** `list_tree` emits an optional `size` for doc/file nodes.
11. All pre-existing tests stay green; the full suite runs in < 2 minutes.

## 5. Test plan

> All tests combined must keep the suite under 2 minutes. Prefer deterministic
> `_poll` waits over fixed sleeps. No new slow (LaTeX/LLM) work is introduced.

- **Backend (pytest):**
  - `test_collab_manager.py`: compaction-trigger test (issue 105).
  - `test_collab_ws_refactor.py`: poll-based waits (issue 113) + `_setup` return
    type (issue 116).
  - `test_collab_refactor.py`: reordered-update convergence test (issue 114) +
    concurrent-eviction swap-race test (issue 115).
  - `test_db_session.py`: Ping timestamp/updated_at bump assertions (issue 9).
  - `list_tree.py`: verify the `size` field via any existing agent-tool test that
    is in scope; if the only `list_tree` test is out of scope, implement the
    field and **report** that the assertion should be added by the owning pack.
- **Frontend (Vitest):**
  - `file-tree/types.ts`: type-only change (issue 60) — verified by `tsc`.
  - `editor/types.ts` + `editor/api.ts`: `name` mapping (issue 64) — verified by
    `tsc` and any existing api mapping test in scope.
  - `HistoryTimeline.test.tsx`: focusability/keyboard test (issue 155).
- **Performance/budget note:** poll-based waits keep timing tight; run
  `just test-timed` to confirm < 2 minutes.

## 6. Definition of Done

- [ ] All 10 issues in §3 resolved; none invented, none dropped.
- [ ] Deterministic `_poll` waits replace positive-condition sleeps (issue 113);
      only the non-eviction negative check keeps a bounded sleep.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green (or reported where an
      out-of-scope source/test edit would be required).
- [ ] No files edited outside §2.
- [ ] Full suite runs in < 2 minutes (`just test-timed`).
- [ ] Lint/format/type-check clean (ruff + pyright on backend; ESLint + tsc on
      frontend).
- [ ] No Overleaf code copied; stack unchanged.
