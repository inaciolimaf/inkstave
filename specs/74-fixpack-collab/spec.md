# Spec 74 — Fix-pack: collaboration, editor settings & agent-scope cleanups (requirements)

## 1. Summary

This fix-pack applies **9 confirmed issues** drawn from specs
`05-refactor-foundations`, `18-editor-ui-codemirror`,
`22-compile-api-async-jobs`, `31-frontend-yjs-binding`,
`32-presence-awareness-ui`, and `41-agent-foundation`. They were each verified by
two independent reviewers.

**Severity breakdown (adjusted):**

- **Major:** 1 — #62 missing keymap selector in the editor settings popover.
- **Minor:** 5 — #119 live concurrent-insert CRDT convergence test; #120
  deterministic reconnect test (no real timer); #118 undo-scoping test; #124
  awareness-throttle integration test; #165 agent spec-41 forward-wiring note.
- **Nit:** 3 — #125 duplicated `CURSOR_THROTTLE_MS` constant; #15 missing
  `commit` column in the refactor-05 findings table; #82 `CompileRepository`
  named-method contract (`set_status`/`set_result`).

The bulk of the work is **test completeness** (CRDT/undo/throttle properties that
the source specs required but were never asserted) plus one real **UI gap** (the
keymap selector) and small **interface/documentation** alignments.

## 2. Files in scope

Edit **only** these files (exact payload set). Touching anything else breaks the
parallel-safety guarantee of this fix-pack.

- `backend/src/inkstave/agent/runner.py`
- `backend/src/inkstave/agent/state.py`
- `backend/src/inkstave/compile/repository.py`
- `docs/refactors/05-foundations.md`
- `frontend/src/features/collab/CollabEditor.test.tsx`
- `frontend/src/features/collab/InkstaveWsProvider.test.ts`
- `frontend/src/features/collab/throttle.test.ts`
- `frontend/src/features/collab/useCollabDoc.ts`
- `frontend/src/features/collab/usePresence.ts`
- `frontend/src/features/editor/editor-settings-popover.tsx`

> **Restrict-edits note:** Do not modify any production source beyond
> `useCollabDoc.ts`, `usePresence.ts`, `editor-settings-popover.tsx`,
> `runner.py`, `state.py`, and `repository.py`. The remaining files are tests and
> docs. Do not create new files unless a test file must be split (prefer adding
> cases to the existing test files listed above).

## 3. Issues to fix

### Issue #62 — Keymap selector missing from the editor settings popover (MAJOR)

- **Source spec:** 18-editor-ui-codemirror (§5.3.5 item 3; AC6).
- **File:** `frontend/src/features/editor/editor-settings-popover.tsx`.
- **Problem:** Spec §5.3.5 requires the per-editor settings popover to let the
  user change **font size, keymap, and line wrapping**, and AC6 requires that a
  keymap change from the popover applies live to the open editor. The current
  popover (verified) exposes only a font-size `Select` and a line-wrapping
  `Switch`; `grep -n 'keymap'` in the file returns nothing. Keymap is only
  exposed in the global settings page (spec 59).
- **Fix to apply:** Add a keymap `Select` to `EditorSettingsPopover`, wired to
  `onUpdate({ keymap })`. Use the existing `EditorKeymap` type
  (`type EditorKeymap = "default" | "vim" | "emacs"`, already imported via
  `EditorSettings.keymap`). Mirror the existing font-size `Select` pattern:
  - bind `value={settings.keymap}` and `onValueChange={(v) => onUpdate({ keymap: v as EditorKeymap })}`;
  - options: `default`, `vim`, `emacs` (labels e.g. "Default", "Vim", "Emacs");
  - give the trigger a `label` + `aria-label="Keymap"` and an `id` consistent
    with the existing controls.
  The keymap value already flows through `keymapExtension()` (verified in
  `frontend/src/features/editor/keymap-extension.ts`), so wiring `onUpdate` is
  sufficient for the change to apply live and persist.

### Issue #119 — Live concurrent-insert CRDT convergence test missing (minor)

- **Source spec:** 31-frontend-yjs-binding (§8).
- **File:** `frontend/src/features/collab/InkstaveWsProvider.test.ts`.
- **Problem:** §8 requires a test where **both A and B insert simultaneously
  while live** and both converge to identical text (the CRDT property). The
  existing tests cover only sequential propagation (A inserts → B receives) and
  offline-vs-server edits; a true two-live-client concurrent insert is absent.
- **Fix to apply:** Add a test in `InkstaveWsProvider.test.ts` where two live
  clients (two `Y.Doc`s wired through the provider/relay harness already used in
  this file) each insert at the **same position** in the same tick, then flush
  the transport and assert `a.text === b.text` **and** that both equal the
  server/relayed text. Use the file's existing fake-timer/relay helpers; do not
  introduce real timers.

### Issue #120 — Reconnect test uses a real wall-clock timer (minor)

- **Source spec:** 31-frontend-yjs-binding (AC4).
- **File:** `frontend/src/features/collab/InkstaveWsProvider.test.ts`.
- **Problem:** The AC4 offline-reconnect test uses
  `await new Promise((r) => setTimeout(r, 700))` with **real timers**, waiting
  out the 0–500 ms backoff jitter. This adds ~500–700 ms of real wall-clock per
  run and can flake if jitter lands near 700 ms. Other tests in the file
  correctly use `vi.useFakeTimers()` / `vi.advanceTimersByTimeAsync()`.
- **Fix to apply:** Convert the reconnect test to **fake timers**: set up
  `vi.useFakeTimers()` for the convergence/reconnect block and advance past the
  deterministic backoff with `vi.advanceTimersByTimeAsync(...)`. To remove
  non-determinism from the jitter, **stub/seed the jitter** (e.g. stub
  `Math.random` to a fixed value, or whatever jitter source the provider uses)
  so the backoff delay is exact, then advance precisely past it. The test must
  add **no** real wall-clock wait.

### Issue #118 — Undo-scoping (AC9) test missing (minor)

- **Source spec:** 31-frontend-yjs-binding (AC9).
- **Files:** `frontend/src/features/collab/useCollabDoc.ts` (production wiring,
  already present), `frontend/src/features/collab/CollabEditor.test.tsx` and/or
  `frontend/src/features/collab/InkstaveWsProvider.test.ts` (new test).
- **Problem:** AC9 requires a test that **undo after typing reverts only the
  local user's most recent change group, not remote edits**. The `UndoManager`
  is created and passed to `yCollab` in `useCollabDoc.ts` (verified ~lines
  82–93) but its scoping is never asserted anywhere in the suite.
- **Fix to apply:** Add an in-process collab test using two `Y.Doc`s:
  1. the local doc types a change group (tagged with the local origin used by
     the binding's `UndoManager`);
  2. the remote doc makes an edit that propagates in;
  3. trigger the binding's **undo** (via the same `UndoManager`/origin the
     production code wires up);
  4. assert that **only** the local change group is reverted and the remote
     edit **remains** in the document.
  Reuse the `UndoManager`/origin wiring exactly as in `useCollabDoc.ts`; do not
  change the production undo configuration unless the test reveals a real
  scoping defect (if it does, fix it minimally in `useCollabDoc.ts` and note it).

### Issue #124 — Awareness-throttle integration test missing (minor)

- **Source spec:** 32-presence-awareness-ui (§8).
- **Files:** `frontend/src/features/collab/throttle.test.ts` and/or
  `frontend/src/features/collab/InkstaveWsProvider.test.ts`.
- **Problem:** §8 requires "simulated rapid selection changes emit a bounded
  number of awareness updates (mock timers)". `throttle.test.ts` only tests the
  generic `throttle()` utility in isolation; the integration path
  `InkstaveWsProvider._onAwarenessUpdate → _pendingAwareness → _flushAwareness`
  is never exercised, so the property that rapid awareness changes collapse to a
  **bounded** number of wire frames is unverified.
- **Fix to apply:** Add an `InkstaveWsProvider` test that:
  - constructs the provider with a configured `awarenessThrottleMs` (the option
    the provider already accepts);
  - uses **fake timers** and triggers many rapid `awareness.setLocalState(...)`
    changes within one throttle window;
  - asserts that the number of **awareness frames** pushed to the controllable
    WS transport (the existing `sent: Uint8Array[]` capture in the harness) is
    **bounded** (leading + trailing, i.e. small constant — not one per change).
  Keep this in `InkstaveWsProvider.test.ts` (the harness with `sent` lives
  there); leave `throttle.test.ts` as-is for the utility unless you add a
  clarifying assertion there too.

### Issue #165 — Agent spec-41 forward-wiring scope note (minor)

- **Source spec:** 41-agent-foundation (§4 non-goals).
- **Files:** `backend/src/inkstave/agent/state.py`,
  `backend/src/inkstave/agent/runner.py` (plus the changelog note lives in
  `docs/refactors/05-foundations.md`? **No** — see below).
- **Problem:** `AgentState` in `state.py` carries `staged_edits`
  (`Annotated[list[StagedEdit], operator.add]`, a spec-42 concept) and a `usage`
  field, and `runner.py` already calls `materialize_diffs()` (spec 43). Spec 41
  §4 explicitly lists "Diff generation / proposed_diffs — spec 43" and tools
  (spec 42) as **non-goals**. The code works for spec-41 use cases but crosses
  the stated spec-41 boundary ("no more, no less").
- **Fix to apply:** This is a **scope-boundary documentation** observation, not a
  behavioural change — the later specs (42/43) legitimately build on these same
  files, so **do not remove** the forward-wired fields/calls (that would break
  42/43). Instead, add a short **code comment** at the relevant points in
  `state.py` (on `staged_edits` / `usage`) and `runner.py` (at the
  `materialize_diffs` call) noting that these are **forward-wired for specs
  42/43** and were intentionally introduced ahead of strict per-spec boundaries.
  Keep the comments brief and factual. Do not edit out-of-scope files for this.

### Issue #125 — Duplicated `CURSOR_THROTTLE_MS` constant (nit)

- **Source spec:** 32-presence-awareness-ui.
- **Files:** `frontend/src/features/collab/usePresence.ts` (exporter),
  `frontend/src/features/collab/useCollabDoc.ts` (duplicate).
- **Problem:** `usePresence.ts` exports `CURSOR_THROTTLE_MS = 50` but
  `useCollabDoc.ts` defines its **own private** `const CURSOR_THROTTLE_MS = 50`
  instead of importing the exported one. A future change to one would silently
  not affect the other.
- **Fix to apply:** In `useCollabDoc.ts`, **import** `CURSOR_THROTTLE_MS` from
  `./usePresence` and **delete** the local duplicate constant. Confirm no other
  symbol-name collision is introduced.

### Issue #15 — Missing `commit` column in the refactor-05 findings table (nit)

- **Source spec:** 05-refactor-foundations (§5.2).
- **File:** `docs/refactors/05-foundations.md`.
- **Problem:** §5.2 lists `commit` ("short SHA / link if applied") as a required
  field of the findings catalogue table, but the table header omits it. The
  prose explains no per-spec commits exist, but the column itself is absent.
- **Fix to apply:** Add a `commit` column to the findings table. Populate it with
  the short SHA where a finding maps to a commit, or `—` where no per-spec commit
  exists (consistent with the existing prose). Keep all existing columns and rows
  intact; only add the column.

### Issue #82 — `CompileRepository` named-method contract (nit)

- **Source spec:** 22-compile-api-async-jobs (§5.2.6).
- **File:** `backend/src/inkstave/compile/repository.py`.
- **Problem:** §5.2.6 names two specific methods — `set_status(...)` and
  `set_result(...)`. The implementation provides only a generic
  `update(self, row, **fields)`. Functionally equivalent, but the named-interface
  contract is unmet.
- **Fix to apply:** Add thin `set_status(...)` and `set_result(...)` wrapper
  methods on `CompileRepository` that **delegate to the existing `update(...)`**.
  Give them precise type signatures matching the fields they set (status; result
  fields), keep them async, and do not change `update`'s behaviour. Existing
  callers may keep using `update`; the wrappers satisfy the spec contract and are
  available for use.

## 4. Acceptance criteria

1. **Keymap selector (#62):** The editor settings popover renders a keymap
   `Select` with options default/vim/emacs; choosing one calls
   `onUpdate({ keymap })` and the editor applies the new keymap live. A Vitest
   asserts the control exists and fires `onUpdate` with the chosen keymap.
2. **Live CRDT convergence (#119):** A new test has two live clients insert at
   the same position concurrently and asserts both docs and the relayed/server
   text are identical.
3. **Deterministic reconnect (#120):** The reconnect test uses fake timers and a
   seeded/stubbed jitter; it contains **no** real `setTimeout`/`Promise` wall
   wait, and passes deterministically.
4. **Undo scoping (#118):** A new test proves that triggering the binding's undo
   after a local change group reverts only the local change and leaves a
   concurrent remote edit intact.
5. **Awareness throttle integration (#124):** A new `InkstaveWsProvider` test
   drives many rapid awareness updates with fake timers and asserts the awareness
   wire-frame count is bounded (small constant, not one-per-change).
6. **Agent scope note (#165):** `state.py` and `runner.py` carry brief comments
   marking the spec-42/43 forward-wired fields/calls as intentional; no
   behavioural change; specs 42/43 still work and their tests stay green.
7. **Single constant (#125):** `useCollabDoc.ts` imports `CURSOR_THROTTLE_MS`
   from `usePresence` and has no local duplicate; only one definition exists in
   the collab feature.
8. **Findings table (#15):** `docs/refactors/05-foundations.md` findings table
   has a `commit` column with SHA or `—` per row.
9. **Named repo methods (#82):** `CompileRepository` exposes `set_status(...)`
   and `set_result(...)` delegating to `update(...)`, with matching async
   signatures; existing behaviour unchanged.

## 5. Test plan

> The whole suite must stay under 2 minutes. No new real wall-clock waits.

- **Existing green:** Run the full frontend (Vitest) and backend (pytest) suites
  before and after; they must remain green.
- **Vitest (frontend):**
  - `editor-settings-popover` — render the popover, select a keymap, assert
    `onUpdate({ keymap })` fired (covers #62/AC1).
  - `InkstaveWsProvider.test.ts` — add: concurrent live-insert convergence
    (#119/AC2); fake-timer + seeded-jitter reconnect (#120/AC3); awareness
    throttle bounded-frame count (#124/AC5).
  - undo-scoping test in `CollabEditor.test.tsx` or `InkstaveWsProvider.test.ts`
    (#118/AC4).
  - `useCollabDoc.ts` still imports the shared constant after #125; no test
    breakage.
- **pytest (backend):**
  - Add/extend a unit test for `CompileRepository.set_status`/`set_result`
    delegating to `update` (#82/AC9). Existing compile and agent tests stay
    green (the #165 comments are non-functional).
- **Performance/budget note:** The reconnect test conversion (#120) **removes**
  ~700 ms of real wall-clock; all new tests use fake timers / in-process Y.Docs
  and add negligible time.

## 6. Definition of Done

- [ ] All 9 issues in §3 applied; no files outside §2 touched.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; full suite < 2 minutes.
- [ ] No real wall-clock waits introduced; #120 test is deterministic.
- [ ] Lint/format/type-check clean (ruff + mypy/pyright; ESLint + Prettier,
      strict TS).
- [ ] No unrelated refactors; no Overleaf code copied.
- [ ] Specs 42/43 behaviour unchanged by the #165 comments; their tests stay
      green.
