# Spec 83 — Fix-pack: backend/frontend test & behaviour gaps (batch 11) (requirements)

## 1. Summary

This fix-pack remediates nine confirmed issues found during the validation pass.
They span the notifications bell (missing true optimistic dismiss with rollback,
plus the loading/error/rollback tests that cover it), missing unit-level tests
for the agent tools and the binary-file storage helpers, an unimplemented idle
remote-cursor fade (the "faded cursor" half of presence AC6), two missing
exported project types, and an absent explicit Vitest `pool` configuration. Every
issue is a small, localised fix or a focused added test. The files in scope are
disjoint from all other fix-packs, so this work is parallel-safe.

## 2. Files in scope

Edit **only** these files (exact set from the validation payload):

- `backend/tests/unit/test_agent_tools_unit.py`
- `backend/tests/unit/test_storage.py`
- `frontend/src/features/collab/OnlineUsers.tsx`
- `frontend/src/features/collab/remote-cursors.ts`
- `frontend/src/features/notifications/NotificationsBell.test.tsx`
- `frontend/src/features/notifications/useNotifications.ts`
- `frontend/src/features/projects/types.ts`
- `frontend/vitest.config.ts`

Do not modify any file outside this list. Other fix-packs may be editing other
files at the same time. If a fix appears to require touching an out-of-scope
file, stop and flag it rather than expanding scope.

## 3. Issues to fix

### Issue 156 — Dismiss mutation is not a true optimistic update (minor)

- **Source spec:** 39-notifications-email
- **File(s):** `frontend/src/features/notifications/useNotifications.ts`
- **Problem:** The dismiss mutation does not implement a true optimistic update.
  Today (lines ~38–43) it is
  `useMutation({ mutationFn: dismissNotification, onSuccess: invalidate, onError: invalidate })`
  — there is no `onMutate` that removes the item from the cache immediately and
  no rollback in `onError`. The dismissed item therefore stays visible until the
  server responds, which contradicts spec 39 §5.3 ("Dismiss: an × removes the
  item (calls DELETE; optimistic with rollback on error)") and AC 11.
- **Fix to apply:** Convert the dismiss mutation to a true optimistic update:
  1. `onMutate(id)`: call `queryClient.cancelQueries` for the notifications
     query key, snapshot the current cached value, remove the dismissed item
     from the cache immediately (`setQueryData`), and return the snapshot as
     context.
  2. `onError(_err, _id, context)`: restore the snapshotted cache value from
     `context` (rollback).
  3. `onSettled`: call `invalidate` (replaces the previous `onSuccess`/`onError`
     invalidate) so the cache reconciles with server truth in both paths.
  Match the existing query-key and `invalidate` helper already used in the file.

### Issue 162 — Optimistic rollback for dismiss not explicitly tested (nit)

- **Source spec:** 40-refactor-history
- **File(s):** `frontend/src/features/notifications/NotificationsBell.test.tsx`,
  `frontend/src/features/notifications/useNotifications.ts`
- **Problem:** The §5.1 checklist item "Frontend bell: optimistic update
  rollback" is listed for audit. The current dismiss test (lines ~63–76) only
  verifies the happy-path API call; no Vitest test exercises the error path of
  dismiss to confirm the rollback behaviour.
- **Fix to apply:** Add a Vitest test that mocks `dismissNotification` to reject,
  triggers the dismiss action, and asserts the rollback: after the optimistic
  removal added in Issue 156, the dismissed notification reappears in the list
  (and the list reconciles with server truth via the `onSettled` invalidate).
  This issue is satisfied jointly with the rollback test added under Issue 157.

### Issue 157 — Missing loading/error/rollback state tests (minor)

- **Source spec:** 39-notifications-email
- **File(s):** `frontend/src/features/notifications/NotificationsBell.test.tsx`
- **Problem:** The test file covers badge count, list rendering, mark-read,
  dismiss (API call only), Accept, and empty state — but is missing tests for
  (a) the loading skeleton state, (b) the error/retry state, and (c) the dismiss
  rollback-on-error scenario. Spec 39 §8 explicitly lists "empty/loading/error
  states" and "dismiss (optimistic + rollback)" as required Vitest coverage.
- **Fix to apply:** Add three `it()` tests to `NotificationsBell.test.tsx`:
  1. **Loading:** render with `listNotifications` left pending and assert the
     loading skeleton is shown (e.g. an element with `aria-busy="true"` or the
     skeleton testid the component already renders — match the component).
  2. **Error/retry:** render with `listNotifications` rejected and assert the
     error + retry UI appears.
  3. **Dismiss rollback:** render with a populated list, mock
     `dismissNotification` to reject, dismiss an item, and assert the item is
     removed optimistically then reappears after the rejection (rollback). This
     test also satisfies Issue 162.
  If the component does not currently expose the exact loading/error affordances
  the tests need, prefer asserting against the affordances it actually renders
  rather than changing component markup (which is out of scope here, except for
  `OnlineUsers.tsx`/`remote-cursors.ts` per the cursor fix). If a tiny,
  test-visible attribute is genuinely missing, it may be added to
  `useNotifications.ts` consumers only via the in-scope files.

### Issue 170 — Missing Args-schema unit tests for three tools (minor)

- **Source spec:** 42-agent-tools
- **File(s):** `backend/tests/unit/test_agent_tools_unit.py`
- **Problem:** Spec 42 §8 requires unit tests for each tool's Args schema
  validation (happy + invalid_args). Only `ReadFileArgs` and `ProposeEditArgs`
  have unit-level schema tests. `SearchProjectArgs` (empty query), `ListTreeArgs`,
  and `LocateSectionArgs` (empty name) have no dedicated unit schema tests.
- **Fix to apply:** Add unit tests asserting:
  - `SearchProjectArgs(query="")` raises a Pydantic `ValidationError` (invalid),
    and a non-empty query validates (happy).
  - `LocateSectionArgs(name="")` raises a `ValidationError` (invalid), and a
    non-empty name validates (happy).
  - `ListTreeArgs(...)` constructs successfully for a valid input (happy case).
  Import the Args models from the same module the existing tests import from;
  match the existing test style and assertion helpers.

### Issue 172 — search_project ranking/snippet-length unit tests missing (nit)

- **Source spec:** 42-agent-tools
- **File(s):** `backend/tests/unit/test_agent_tools_unit.py`
- **Problem:** Spec 42 §8 lists "search_project ranking, snippet length,
  truncated behavior (AC 2)" as a unit test requirement. These behaviours are
  only exercised via the integration fixture; no pure unit test drives them over
  a synthetic in-memory corpus to verify the 240-char snippet cap or the 8 KB
  payload soft-cap (`truncated: true`) behaviour.
- **Fix to apply:** Add a unit test that drives `search_project` (or its snippet/
  ranking helper functions) over a small synthetic in-memory corpus and asserts:
  - each returned snippet is capped at 240 characters; and
  - when the corpus would exceed the 8 KB payload soft-cap, the result reports
    `truncated: true` (or the equivalent field the implementation uses).
  Use whatever in-memory project/repository test double the existing tests use;
  keep the corpus small and synthetic so the test stays fast.

### Issue 42 — Missing storage unit tests (streaming helper + atomic write) (minor)

- **Source spec:** 14-binary-file-storage
- **File(s):** `backend/tests/unit/test_storage.py`
- **Problem:** Spec 14 §8 requires two unit-level tests that are absent:
  (a) the streaming hash+size+limit helper — "counts bytes, aborts past limit,
  computes sha256 correctly (multi-chunk)"; today this is only covered indirectly
  via integration tests; and (b) `LocalObjectStore` atomic write (temp→replace)
  — no unit test verifies that `LocalObjectStore.put` writes to a temp file then
  replaces atomically.
- **Fix to apply:** Add two unit tests:
  1. **Streaming helper:** feed multi-chunk input through the streaming hash/size/
     limit helper and assert the byte count is correct, the computed sha256
     matches the reference `hashlib.sha256` digest, and that exceeding the limit
     raises the expected `FileTooLarge` (or equivalently named) error.
  2. **Atomic write:** assert `LocalObjectStore.put` creates a temporary file and
     then performs `os.replace` (e.g. monkeypatch `os.replace` to record that it
     was called, and that a `.tmp`-style path existed before the replace), so the
     temp→replace ordering is observed.
  Import the helper and `LocalObjectStore` from the same modules the existing
  storage tests/source use (`backend/src/inkstave/storage/local.py`).

### Issue 123 — Idle remote-cursor fade not implemented (major)

- **Source spec:** 32-presence-awareness-ui
- **File(s):** `frontend/src/features/collab/remote-cursors.ts`,
  `frontend/src/features/collab/OnlineUsers.tsx`
- **Problem:** AC6 states: "their avatar dims and their cursor fades on other
  clients." The avatar is dimmed (`opacity-50` in `OnlineUsers.tsx`), but the
  remote caret decoration in `remote-cursors.ts` has no idle-state fading rule:
  `y-codemirror.next` does not natively consume an `idle` awareness field to
  reduce caret opacity. The "faded cursor" half of AC6 is unimplemented.
- **Fix to apply:** Make an idle peer's remote caret visibly fade on other
  clients:
  1. In `remote-cursors.ts`, read the peer's `idle` awareness field (the same
     field `OnlineUsers.tsx` uses to dim the avatar) when building the remote
     caret/selection decoration, and tag the decoration for idle peers (e.g. add
     an `cm-ySelectionCaret--idle` class / data attribute, or set reduced
     opacity directly on the caret widget).
  2. Add a CSS rule (in the same module's injected styles) that reduces the
     `.cm-ySelectionCaret` (and, if appropriate, `.cm-ySelectionInfo` label)
     opacity for idle peers, so the caret fades.
  3. Keep `OnlineUsers.tsx` consistent: ensure the `idle` field it consumes for
     avatar dimming is the same one the caret decoration reads (refactor only as
     needed to share the field; no behaviour change to the avatar dimming).
  Keep the existing hover-show behaviour of the name label intact.

### Issue 224 — Vitest pool not explicitly configured (minor)

- **Source spec:** 53-performance-test-speed
- **File(s):** `frontend/vitest.config.ts`
- **Problem:** The Vitest config has no explicit `pool` setting. Spec 53 §5.3 /
  AC10 require `pool: 'threads'` (or `'forks'`) with `poolOptions` worker count
  tuned for CI cores. Vitest 2.x parallelises by default, but the spec-mandated
  explicit configuration is absent (the `test` block has only `environment`,
  `globals`, `setupFiles`, `include`).
- **Fix to apply:** Add `pool: 'threads'` and a `poolOptions` block to the
  `test` configuration, with a tuned `maxThreads` (and `minThreads` if
  appropriate) suitable for CI cores. Keep the existing keys unchanged. Do not
  alter test behaviour beyond making the parallelism explicit.

### Issue 52 — Missing exported project types (minor / nit)

- **Source spec:** 16-project-dashboard-ui
- **File(s):** `frontend/src/features/projects/types.ts`
- **Problem:** Spec 16 §5.1 specifies three TypeScript types to be exported from
  `types.ts`: `Project`, `ProjectListResponse`, and `CreateProjectRequest`. Only
  `Project` and `SortKey` are present; `ProjectListResponse` and
  `CreateProjectRequest` are absent (the wire format lives as a private
  `ProjectListWire` in `api.ts` and `name` is passed as a raw `string`).
- **Fix to apply:** Export the two missing types from `types.ts`:
  - `export interface ProjectListResponse { projects: Project[] }`
  - `export interface CreateProjectRequest { name: string }`
  Keep the existing `Project` and `SortKey` exports unchanged. (Wiring these
  types into `api.ts` is out of scope for this pack — `api.ts` is not in the
  files-in-scope list — so only add the exports here; do not edit `api.ts`.)

## 4. Acceptance criteria

1. **(156)** The dismiss mutation in `useNotifications.ts` has an `onMutate` that
   cancels the relevant query, snapshots the cache, and removes the dismissed
   item immediately; an `onError` that restores the snapshot; and an `onSettled`
   that invalidates the notifications query.
2. **(162 + 157c)** A Vitest test mocks `dismissNotification` to reject and
   asserts the dismissed item reappears (rollback) after optimistic removal.
3. **(157a)** A Vitest test asserts the loading skeleton/`aria-busy` state when
   `listNotifications` is pending.
4. **(157b)** A Vitest test asserts the error + retry UI when `listNotifications`
   rejects.
5. **(170)** Unit tests assert `SearchProjectArgs(query="")` and
   `LocateSectionArgs(name="")` raise validation errors, a non-empty value for
   each validates, and `ListTreeArgs` constructs for a valid input.
6. **(172)** A unit test drives `search_project` (or its helpers) over a
   synthetic corpus and asserts the 240-char snippet cap and the 8 KB payload
   soft-cap `truncated: true` behaviour.
7. **(42)** Unit tests assert the streaming helper computes the correct
   sha256/byte-count over multi-chunk input and raises `FileTooLarge` past the
   limit, and that `LocalObjectStore.put` writes to a temp file then `os.replace`s.
8. **(123)** An idle peer's remote caret visibly fades on other clients: the
   caret decoration is conditioned on the `idle` awareness field and a CSS rule
   reduces its opacity for idle peers, while avatar dimming in `OnlineUsers.tsx`
   continues to work off the same field.
9. **(224)** `vitest.config.ts` declares an explicit `pool` (`'threads'` or
   `'forks'`) with a `poolOptions` worker count.
10. **(52)** `types.ts` exports `ProjectListResponse` and `CreateProjectRequest`
    alongside the existing `Project` and `SortKey`.

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Existing tests stay green:** Run the backend unit suite
  (`backend/tests/unit/`) and the affected frontend Vitest suites; all currently
  passing tests must remain green.
- **New/updated frontend tests (Vitest):** the three added
  `NotificationsBell.test.tsx` tests (loading, error/retry, dismiss rollback).
  These mock `listNotifications`/`dismissNotification` — no real network. Verify
  the idle-cursor change does not break existing collab unit tests.
- **New backend unit tests (pytest):** the agent-tools Args validation tests, the
  `search_project` snippet/truncation test, and the storage streaming-helper +
  atomic-write tests. All use in-memory doubles/monkeypatching; no real I/O,
  network, or LLM calls.
- **Performance/budget note:** every new test is a pure unit/component test with
  mocked dependencies; total added runtime is negligible and the full suite stays
  under 2 minutes.

## 6. Definition of Done

- [ ] All nine issues in §3 fixed (156, 162, 157, 170, 172, 42, 123, 224, 52).
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; pre-existing tests still
      green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff for Python; ESLint/Prettier + strict TS
      for frontend).
- [ ] Only files listed in §2 were modified.
- [ ] No Overleaf code copied.
