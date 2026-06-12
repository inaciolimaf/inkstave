# Spec 80 — Fix-pack: backend/frontend test & interface gaps (batch 8) (requirements)

## 1. Summary

This fix-pack applies **9 confirmed issues** validated by two independent
reviewers. They span missing test coverage and small interface/label deviations
across five source specs: autosave (REST), frontend foundation (auth),
compile-error annotations, collaborators/sharing, and agent-safety evals.

Severity breakdown (adjusted severity):
- **major:** 0
- **minor:** 7 (IDs 69, 70, 128, 129, 26, 101, 130; ID 206 adjusted to minor)
- **nit:** 1 (ID 71)

(ID 206 was originally filed as major but adjusted to minor by review; it is the
one behavioural-coverage gap for the disallowed-tool audit event.)

Source specs touched: `09-frontend-foundation`, `19-document-autosave-rest`,
`27-compile-error-annotations`, `33-collaborators-sharing`,
`49-agent-safety-evals`.

## 2. Files in scope

Edit **only** these files (exact payload set). Do not modify anything outside
this list — other fix-packs run in parallel on disjoint files.

- `backend/tests/agent_evals/test_agent_evals.py`
- `backend/tests/integration/test_agent_safety_api.py`
- `backend/tests/integration/test_sharing_api.py`
- `backend/tests/unit/test_sharing_service.py`
- `frontend/src/auth/auth-context.tsx`
- `frontend/src/features/editor/diagnostics.test.ts`
- `frontend/src/features/editor/editor-pane.tsx`
- `frontend/src/features/editor/save-status-indicator.tsx`

> Restrict-edits note: if a fix appears to need a change in a file not listed
> above, stop — it belongs to a different fix-pack. Prefer the smallest change
> that satisfies the issue within the in-scope files.

## 3. Issues to fix

### Issue 69 — Ctrl/Cmd+S acceptance criterion untested
- **Source spec:** 19-document-autosave-rest
- **Severity:** minor
- **File(s):** `frontend/src/features/editor/editor-pane.tsx`
- **Problem:** AC11 of spec 19 states: "Given Ctrl/Cmd+S (if implemented), then
  an immediate flush occurs and the browser's native save dialog is suppressed."
  Ctrl/Cmd+S **is** implemented in `editor-pane.tsx` (keydown handler ~lines
  154-165: `e.preventDefault()` then `saveNow`), but no unit/integration/E2E test
  exercises the keydown handler. A grep for `Ctrl|metaKey|ctrlKey|keydown|save.*key`
  across `frontend/src/features/editor/**/*.test.*` returns nothing.
- **Fix to apply:** Add a component test (co-located test file for `EditorPane`,
  e.g. `frontend/src/features/editor/editor-pane.test.tsx` — a new test file is in
  scope because it tests an in-scope component) that renders the editor, dispatches
  a `keydown` event with `metaKey`/`ctrlKey` + `s`, and asserts (a) `saveNow`/the
  flush callback is invoked and (b) `event.preventDefault()` is honored (the
  default action is suppressed). Mock the autosave hook so `saveNow` is a spy.
  Keep the test fast (no real network).

### Issue 71 — SaveStatusIndicator label text deviates from spec
- **Source spec:** 19-document-autosave-rest
- **Severity:** nit
- **File(s):** `frontend/src/features/editor/save-status-indicator.tsx`
- **Problem:** Spec 19 §5.3.3 specifies the labels `error` → "Save failed —
  retrying" and `offline` → "Offline — changes will save when you reconnect". The
  implementation currently uses the shortened "Save failed" (line ~16) and
  "Offline" (line ~20). The co-located `save-status-indicator.test.*` asserts the
  shorter labels too.
- **Fix to apply:** Change the `error` label to `Save failed — retrying` and the
  `offline` label to `Offline — changes will save when you reconnect`. Update the
  `save-status-indicator` test assertions to match the new descriptive text.

### Issue 70 — relative timestamp missing from "Saved" status indicator
- **Source spec:** 19-document-autosave-rest
- **Severity:** minor
- **File(s):** `frontend/src/features/editor/save-status-indicator.tsx`,
  `frontend/src/features/editor/editor-pane.tsx`
- **Problem:** Spec 19 §5.3.3 specifies `clean` → "Saved" plus a relative time
  (e.g. "Saved just now"). The autosave hook returns `lastSavedAt: number | null`,
  but `EditorPane` does not forward it to `<SaveStatusIndicator>`, and the
  component's CONFIG for `clean` only has `label: 'Saved'` with no time display.
- **Fix to apply:** Add an optional `lastSavedAt?: number | null` prop to
  `SaveStatusIndicator`. When `status === 'clean'` and `lastSavedAt` is set, render
  a relative timestamp suffix (e.g. "Saved just now" for very recent, otherwise a
  short relative phrase). Forward `lastSavedAt` from `EditorPane` to the
  `<SaveStatusIndicator>` render. Keep the existing static "Saved" label as the base
  when `lastSavedAt` is null. Update/extend the indicator test to cover the
  relative-time rendering for the clean state.

### Issue 128 — expired-invite decline path untested (AC4)
- **Source spec:** 33-collaborators-sharing
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_sharing_api.py`
- **Problem:** Spec 33 AC4: "Given an expired invite, when accept/decline is
  attempted, then the API returns 410 and no membership is created." The existing
  `test_expired_invite_returns_410` only POSTs `.../accept`; the decline path is
  not tested.
- **Fix to apply:** Add a test (or extend the existing one) that POSTs
  `.../{token}/decline` on an expired invite and asserts the response is `410` and
  that no membership was created. Reuse the same expired-invite setup pattern used
  by the accept test.

### Issue 129 — non-owner 403 sweep omits transfer & remove-other (AC9)
- **Source spec:** 33-collaborators-sharing
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_sharing_api.py`
- **Problem:** Spec 33 AC9: all owner-only endpoints return 403 for a non-owner.
  `test_non_owner_owner_only_endpoints_403` checks POST invites, GET invites, and
  PATCH member role, but omits `DELETE /members/{other_user_id}` (remove-other) and
  `POST /members/transfer`, both owner-only per the spec endpoint table.
- **Fix to apply:** Extend the AC9 test to also assert `403` when a non-owner calls
  `DELETE /members/{other_user_id}` and `POST /members/transfer`. Follow the
  existing assertion style in that test.

### Issue 26 — bootstrap() not exposed in AuthContextValue
- **Source spec:** 09-frontend-foundation
- **Severity:** minor
- **File(s):** `frontend/src/auth/auth-context.tsx`
- **Problem:** Spec 09 (§3, §5.3) requires the auth context to expose a
  `bootstrap()` function. The implementation auto-bootstraps inside a `useEffect`
  on mount (lines ~40-58) but does not expose `bootstrap()` on `AuthContextValue`
  (interface lines ~13-24), so callers cannot trigger it imperatively.
- **Fix to apply:** Extract the bootstrap logic from the mount effect into a named
  (memoized, e.g. `useCallback`) `bootstrap` function, call it from the mount
  effect, and add `bootstrap` to the `AuthContextValue` interface and the context
  value object. Keep the existing auto-bootstrap-on-mount behaviour unchanged.

### Issue 101 — multi-file diagnostics filtering untested (AC11)
- **Source spec:** 27-compile-error-annotations
- **Severity:** minor
- **File(s):** `frontend/src/features/editor/diagnostics.test.ts`
- **Problem:** Spec 27 AC11: "problems for *other* files do not appear in the
  current editor." The file-filtering logic lives in `editor-workspace.tsx`
  (`filter((p) => p.file === path)`), but `diagnostics.test.ts` only tests
  `problemsToDiagnostics`/`applyDiagnostics` and never passes a multi-file
  `CompileProblems` payload to verify only the matching file's problems become
  diagnostics.
- **Fix to apply:** Add a unit test in `diagnostics.test.ts` that constructs a
  problems payload referencing **two** different files, applies the same
  current-file filter the editor uses (filter `p.file === path` then
  `problemsToDiagnostics`), and asserts only the current path's problems become
  diagnostics. (Test the pure filter+map contract within this file; do not import
  `editor-workspace.tsx`, which is out of scope — replicate the one-line filter the
  workspace applies.)

### Issue 206 — disallowed-tool call not asserted as `injection_flagged` (AC5)
- **Source spec:** 49-agent-safety-evals
- **Severity:** minor (adjusted from major)
- **File(s):** `backend/tests/integration/test_agent_safety_api.py`,
  `backend/tests/agent_evals/test_agent_evals.py`
- **Problem:** Spec 49 AC5: "Given the model emits a call to a tool not in the
  spec-42 allow-list, it is rejected, logged as `injection_flagged`, and the run
  continues or fails gracefully." The code in `nodes.py:148-158` correctly rejects
  and appends an `injection_flagged` event with `reason='disallowed_tool'`, but no
  test asserts that audit event/row is written for a **disallowed-tool** call. The
  existing `injection_flagged` tests cover only prompt-injection (AC4), and
  `test_act_unknown_tool_is_unsupported` only asserts `ok is False` / code
  `'unsupported'`.
- **Fix to apply:** Add a test that drives the agent to emit a tool call **not** in
  the spec-42 allow-list and asserts an `injection_flagged` audit event is written
  with `detail.reason == 'disallowed_tool'` (and that the run continues or fails
  gracefully, per existing patterns). Place it where the audit-event assertions
  already live — extend `test_agent_safety_api.py` (preferred, it already inspects
  audit events) and/or add an eval case in `test_agent_evals.py` mirroring the
  existing `injection_flagged` eval. Reuse the fake-LLM/scripted-tool-call harness
  used by the existing safety tests rather than calling a real model.

### Issue 130 — missing unit tests for invite expiry & change_role
- **Source spec:** 33-collaborators-sharing
- **Severity:** minor
- **File(s):** `backend/tests/unit/test_sharing_service.py`
- **Problem:** Spec 33 §8 (unit plan) requires unit tests for "role transitions …
  invite expiry computation." `test_sharing_service.py` covers token gen, hashing,
  refresh-existing-pending, accept email matching/case, transfer demotion, and
  transfer-non-member, but has **no** unit asserting `expires_at = now() +
  timedelta(days=ttl_days)`, and **no** `change_role` service unit test. Both are
  only hit indirectly via integration tests.
- **Fix to apply:** Add two unit tests to `test_sharing_service.py`:
  1. `create_invite` with a known `ttl_days=N` asserts `expires_at` is
     approximately `now() + timedelta(days=N)` (use a tolerance window, e.g. within
     a few seconds, to avoid clock flakiness).
  2. `change_role` transitions a member's role (e.g. editor ↔ viewer) successfully
     and rejects setting role to `owner` (matching the service's single-owner
     invariant / validation). Follow the existing service-test setup style.

## 4. Acceptance criteria

1. **(Issue 69)** A test dispatches a `keydown` with `metaKey`/`ctrlKey` + `s` on
   the editor and asserts the save flush callback is invoked **and**
   `preventDefault` is honored; the test passes.
2. **(Issue 71)** `SaveStatusIndicator` renders `error` → "Save failed — retrying"
   and `offline` → "Offline — changes will save when you reconnect"; the indicator
   test asserts the new descriptive labels and passes.
3. **(Issue 70)** `SaveStatusIndicator` accepts `lastSavedAt` and, for the `clean`
   state with a non-null `lastSavedAt`, renders a relative timestamp (e.g. "Saved
   just now"); `EditorPane` forwards `lastSavedAt`; a test covers the clean
   relative-time rendering.
4. **(Issue 128)** An integration test POSTs `.../decline` on an expired invite and
   asserts `410` with no membership created; it passes.
5. **(Issue 129)** The AC9 non-owner sweep additionally asserts `403` for
   `DELETE /members/{other_user_id}` and `POST /members/transfer`; it passes.
6. **(Issue 26)** `AuthContextValue` exposes `bootstrap`, the mount effect calls
   the extracted `bootstrap` function, and existing auth behaviour/tests still pass.
7. **(Issue 101)** A `diagnostics.test.ts` test feeds a two-file problems payload
   through the current-file filter and asserts only the current path's problems
   become diagnostics; it passes.
8. **(Issue 206)** A test asserts an `injection_flagged` audit event with
   `detail.reason == 'disallowed_tool'` is written when the model calls a tool not
   in the allow-list; it passes.
9. **(Issue 130)** Unit tests assert invite-expiry computation (`now() + ttl_days`)
   and `change_role` transitions (including owner rejection); they pass.

## 5. Test plan

> All project tests combined must keep the suite under 2 minutes. No real LLM,
> network, or LaTeX compile in these tests — use the existing fakes/mocks.

- **Existing green:** Run the frontend Vitest suite for the editor/auth files and
  the backend pytest suites for sharing and agent-safety before and after; all
  previously-passing tests must stay green.
- **New/updated frontend tests (Vitest + RTL):**
  - New `editor-pane` Ctrl/Cmd+S test (Issue 69).
  - Updated `save-status-indicator` test for new labels (Issue 71) and clean-state
    relative time (Issue 70).
  - New multi-file filtering case in `diagnostics.test.ts` (Issue 101).
- **New/updated backend tests (pytest + httpx / test DB):**
  - Expired-invite decline 410 (Issue 128) and AC9 transfer/remove-other 403
    (Issue 129) in `test_sharing_api.py`.
  - Invite-expiry and `change_role` unit tests in `test_sharing_service.py`
    (Issue 130).
  - Disallowed-tool `injection_flagged` audit assertion in
    `test_agent_safety_api.py` and/or `test_agent_evals.py` (Issue 206).
- **Performance/budget note:** All additions are pure-function or mocked-IO tests;
  they add negligible runtime. Reuse existing fixtures/fakes; do not add real
  external calls.

## 6. Definition of Done

- [ ] All 9 issues in §3 fixed exactly as described.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; previously-green tests stay
      green.
- [ ] Only files listed in §2 were modified (new test files co-located with
      in-scope components are permitted).
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff + pyright/mypy backend; ESLint + Prettier
      + tsc frontend).
- [ ] No unrelated refactors; no Overleaf code copied.
