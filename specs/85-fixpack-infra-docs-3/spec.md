# Spec 85 — Fix-pack: infra, docs & UI gaps (batch 3) (requirements)

## 1. Summary

This fix-pack remediates nine confirmed issues. Several are documentation
reconciliations: the spec-14 upload acceptance criterion (sanitize vs. reject) now
superseded by spec 52, the spec-20 editor refactor changelog (missing "missing
tests" category and an undocumented dev dependency), and the spec-35 collaboration
changelog (the F-2 dead-code removal with no paired test). The rest are small
frontend UI fixes (agent composer send spinner + shadcn Tooltip, share-dialog
inline errors + skeleton) and added backend/frontend tests (upload/rename
traversal-reserved-control coverage, an editor-preference hook test). Each is a
localised doc edit, a focused test, or a small UI change. The files in scope are
disjoint from all other fix-packs, so this work is parallel-safe.

## 2. Files in scope

Edit **only** these files (exact set from the validation payload):

- `backend/src/inkstave/api/routes/files.py`
- `backend/src/inkstave/security/uploads.py`
- `backend/tests/integration/test_files_api.py`
- `docs/refactors/20-editor-file-tree.md`
- `docs/refactors/35-collaboration.md`
- `frontend/package.json`
- `frontend/src/features/agent/controls.tsx`
- `frontend/src/features/editor/editor-preferences.test.ts`
- `frontend/src/features/editor/use-editor-preferences.ts`
- `frontend/src/features/sharing/ShareDialog.tsx`

Do not modify any file outside this list. Other fix-packs may be editing other
files at the same time. If a fix appears to require touching an out-of-scope
file, stop and flag it rather than expanding scope.

## 3. Issues to fix

### Issue 41 — Upload AC5 (traversal → 422) unmet, superseded by spec 52 (major → minor)

- **Source spec:** 14-binary-file-storage
- **File(s):** `backend/tests/integration/test_files_api.py`,
  `backend/src/inkstave/api/routes/files.py`,
  `backend/src/inkstave/security/uploads.py`
- **Problem:** Spec 14 AC5 states: "Given a name like `../evil` or `a/b`, when
  uploaded, then `422 invalid_name`." Instead the route calls `sanitize_filename()`
  which strips the traversal component (`../evil` → `evil`), then validates the
  sanitized name — so a traversal name with no allowed extension yields
  `415 unsupported_media_type`, not `422 invalid_name`. The test at
  `test_files_api.py:203–207` acknowledges this and asserts 415. This is an
  **intentional cross-spec evolution**: spec 52 §5.2.5 permits "sanitized/rejected".
- **Fix to apply:** Reconcile the documentation/behaviour rather than reverting to
  422. Concretely:
  1. Keep the current sanitize-then-validate behaviour in `files.py` /
     `uploads.py` (it is the intended spec-52 policy). Do **not** reintroduce a
     hard 422 for traversal that would break spec-52 semantics.
  2. In `test_files_api.py`, ensure the relevant test's comment clearly records
     that the 415 outcome is the deliberate spec-52 sanitization policy
     superseding spec-14 AC5 (tighten the existing comment at lines ~203–207 if
     it is unclear), and that nothing is written to storage for such a name.
  3. Add a short in-code note (comment) at the `sanitize_filename()` call site in
     `files.py` explaining that traversal components are stripped per spec 52,
     not rejected per the original spec-14 AC5. No behaviour change to the route.

### Issue 47 — Upload/rename traversal/reserved/control rejection coverage (minor)

- **Source spec:** 15-refactor-projects
- **File(s):** `backend/tests/integration/test_files_api.py`
- **Problem:** AC5 requires "a test asserts traversal/reserved/control-char
  rejection on each" path. The tree-create path is fully parametrized, but the
  upload path only covers MIME-rejection and traversal-sanitization (no
  reserved-name like `con.png` or control-char case), and the rename path's
  `safe_path` coverage is limited to a single traversal case (`..`).
- **Fix to apply:** Extend `test_files_api.py` with upload-path cases for a
  reserved name (e.g. `con.png`) and a control-char name (e.g. `with\x00nul.png`),
  asserting they are sanitized or rejected per the design (matching the actual
  sanitize-then-validate behaviour — assert the concrete observed status/outcome,
  not an aspirational one) and that nothing unsafe is written. If the rename path
  is exercised from this test module, add reserved-name and control-char cases for
  it too; if rename lives in a different test module not in scope, cover the
  reserved/control cases through the upload path only and note the rename gap in a
  test comment. (Do not edit `test_tree_api.py` — it is out of scope.)

### Issue 72 — Editor refactor changelog missing "missing tests" category (minor → nit)

- **Source spec:** 20-refactor-editor
- **File(s):** `docs/refactors/20-editor-file-tree.md`
- **Problem:** AC2 requires "a findings list exists covering all six categories in
  §5.2." The six categories are: correctness/bugs, accessibility,
  re-render/performance, dead code/duplication, **missing tests**, and
  consistency/maintainability. The findings table covers five but conflates the
  "missing tests" dimension into the "correctness (test)" label on F-003/F-004
  rather than using a distinct `missing tests` category.
- **Fix to apply:** Edit the findings table in `docs/refactors/20-editor-file-tree.md`
  so the **"missing tests"** category is explicitly represented: relabel F-003
  and/or F-004 to category `missing tests`, or add a dedicated finding row with
  category `missing tests`, each with the existing risk/value evaluation and
  apply/skip/defer decision. Ensure all six §5.2 categories appear by name.

### Issue 74 — Undocumented/unused dev dependency `@axe-core/playwright` (nit)

- **Source spec:** 20-refactor-editor
- **File(s):** `docs/refactors/20-editor-file-tree.md`, `frontend/package.json`
- **Problem:** `@axe-core/playwright` is listed in `devDependencies` but is never
  imported or used (no `AxeBuilder`/`@axe-core/playwright` hits in `e2e/` or
  `src/`). §5.6 requires dev-only tools to be documented in the changelog; the
  changelog mentions `jest-axe` but not `@axe-core/playwright`.
- **Fix to apply:** Choose one:
  - **Preferred (remove):** remove the unused `@axe-core/playwright` entry from
    `frontend/package.json` `devDependencies` (confirm via grep over `e2e/` and
    `frontend/src/` that it is genuinely unused first). If removed, no changelog
    entry is needed beyond a brief note that it was dropped as unused.
  - **Alternative (document):** if there is a reason to keep it, add an entry to
    the spec-20 changelog Applied-edits section documenting `@axe-core/playwright`,
    its purpose, and its license (MIT/MPL-2.0 as applicable).
  Do not touch the lockfile beyond what the package manager regenerates if you
  remove the dependency; if lockfile regeneration is out of scope/unsafe here,
  prefer the documentation alternative.

### Issue 184 — AgentComposer send button has no spinner while run active (minor)

- **Source spec:** 46-agent-chat-ui
- **File(s):** `frontend/src/features/agent/controls.tsx`
- **Problem:** Spec §5.4 states "Disabled (with spinner on send) while a run is
  starting/streaming." The send button (controls.tsx ~lines 42–53) renders only a
  static `<Send className="size-4" />` with no spinner when `disabled` is true.
- **Fix to apply:** In `controls.tsx`, render `<Loader2 className="size-4
  animate-spin" />` instead of `<Send />` when the run is active (i.e. when the
  button is disabled because a run is starting/streaming). Import `Loader2` from
  `lucide-react` (the icon library already used). Keep the existing
  `disabled={disabled || !value.trim()}` logic and the button's accessible name.
  Distinguish "disabled because empty input" (still show `Send`) from "disabled
  because a run is active" (show the spinner) using the `disabled`/run-active prop
  the component already receives.

### Issue 187 — Send/Stop controls use native `title=` not shadcn Tooltip (nit)

- **Source spec:** 46-agent-chat-ui
- **File(s):** `frontend/src/features/agent/controls.tsx`
- **Problem:** Spec §5.4 lists `Tooltip` among the preferred shadcn/ui primitives
  and says "send/stop buttons have accessible names and tooltips." The controls use
  native HTML `title=` (lines ~48, ~65) and do not import the shadcn `Tooltip`
  (which exists at `components/ui/tooltip.tsx`).
- **Fix to apply:** Wrap the Send and Stop buttons in the shadcn
  `Tooltip`/`TooltipTrigger`/`TooltipContent` (imported from the existing
  `components/ui/tooltip`), moving the `title` text ("Send (Enter)", "Stop") into
  `TooltipContent`. Keep the existing `aria-label` accessible names on the buttons.
  Ensure a `TooltipProvider` is present (add one local to the controls if the
  surrounding tree does not already provide it). No behaviour change beyond the
  tooltip presentation.

### Issue 141 — F-2 dead-code fix has no regression test; changelog gap (nit)

- **Source spec:** 35-refactor-collaboration
- **File(s):** `docs/refactors/35-collaboration.md`
- **Problem:** §5.2 says "For every applied fix, add or update a test that fails
  before and passes after (where feasible)." Fix F-2 (dead-code removal of
  `AuthorizationService`) has no accompanying test, and §8 lists "Regression tests
  for each applied backend fix" without the feasibility qualifier. This is the only
  applied fix without a paired test.
- **Fix to apply:** This is a documentation fix (the only in-scope file is the
  changelog). In `docs/refactors/35-collaboration.md`, update the F-2 entry to
  **explicitly record** that F-2 is a no-behaviour-change dead-code removal of
  `AuthorizationService` for which a paired regression test is not feasible (and
  note that the single role-lookup path is now the only path). This closes the §8
  "regression test per fix" gap by documenting the deliberate exception. Do not add
  a backend test here (no backend test file is in scope for this pack).

### Issue 248 — Editor-preference hook unit test absent (nit)

- **Source spec:** 59-user-settings-profile
- **File(s):** `frontend/src/features/editor/use-editor-preferences.ts`,
  `frontend/src/features/editor/editor-preferences.test.ts`
- **Problem:** Spec §8 requires a Vitest test that "editor-preference hook maps
  stored prefs → CodeMirror config (theme/font/keymap) correctly." The existing
  `editor-preferences.test.ts` tests only the `resolveDark` and `keymapExtension`
  helpers in isolation; there is no test for the `useEditorPreferences` hook
  verifying the full mapping from server-stored `EditorPreferences` to the
  `EditorSettings` object consumed by CodeMirror.
- **Fix to apply:** Add a Vitest test (in `editor-preferences.test.ts`) that renders
  `useEditorPreferences` (use `@testing-library/react`'s `renderHook`) with mock
  server-stored `EditorPreferences` and asserts the resulting `EditorSettings`
  reflects the expected theme, font, and keymap mapping. Mock any data source the
  hook reads from (query/store) so the test is pure and fast. If
  `use-editor-preferences.ts` needs a tiny export adjustment to make the hook's
  output testable (e.g. exporting a type), keep it minimal and within the in-scope
  file.

### Issue 133 — ShareDialog: inline errors and skeleton loading state (nit)

- **Source spec:** 33-collaborators-sharing
- **File(s):** `frontend/src/features/sharing/ShareDialog.tsx`
- **Problem:** Spec §5.3 specifies (1) server-side errors (e.g. "already member")
  should show as inline errors near the form field, not toasts — today
  `toast.error` is used for all server errors (ShareDialog.tsx ~line 100); and
  (2) the loading state should be a shadcn `Skeleton`, but the implementation shows
  plain "Loading…" text (~line 182).
- **Fix to apply:** In `ShareDialog.tsx`:
  1. Surface the **invite mutation** server error (e.g. "already member") as an
     inline message rendered under the email input field (mirroring the existing
     client-side email-validation inline error using `aria-invalid`/an error
     `<p>`), instead of `toast.error`. Keep toasts for other actions only if the
     spec does not require them inline; the invite-already-member case must be
     inline. Capture the error from the mutation's `onError` into local state and
     render it near the field.
  2. Replace the plain "Loading…" text for the members list with a shadcn
     `Skeleton` component (import from the existing `components/ui/skeleton`).

## 4. Acceptance criteria

1. **(41)** The upload route keeps the spec-52 sanitize-then-validate behaviour;
   `test_files_api.py` and an in-code comment clearly record that the 415 outcome
   for `../evil` is the deliberate spec-52 policy superseding spec-14 AC5, and
   nothing is stored for such a name.
2. **(47)** `test_files_api.py` covers reserved-name (e.g. `con.png`) and
   control-char upload cases asserting the actual sanitize/reject outcome and that
   nothing unsafe is written.
3. **(72)** The spec-20 editor refactor changelog findings table explicitly
   includes the `missing tests` category (all six §5.2 categories present by name),
   each with a risk/value evaluation and apply/skip/defer decision.
4. **(74)** `@axe-core/playwright` is either removed from `frontend/package.json`
   devDependencies (confirmed unused) or documented in the spec-20 changelog with
   purpose and license.
5. **(184)** The AgentComposer send button shows `<Loader2 className="size-4
   animate-spin" />` while a run is active and `<Send />` otherwise.
6. **(187)** The Send and Stop buttons are wrapped in shadcn
   `Tooltip`/`TooltipTrigger`/`TooltipContent`, retaining their `aria-label`s.
7. **(141)** The spec-35 collaboration changelog explicitly records F-2 as a
   no-behaviour-change dead-code removal for which a regression test is not
   feasible.
8. **(248)** A Vitest test renders `useEditorPreferences` with mock stored prefs
   and asserts the theme/font/keymap mapping into the CodeMirror `EditorSettings`.
9. **(133)** `ShareDialog.tsx` shows the invite "already member" server error
   inline near the email field (not as a toast) and uses a shadcn `Skeleton` for
   the members-list loading state.

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Existing tests stay green:** Run the backend integration suite for files
  (`backend/tests/integration/test_files_api.py`) and the frontend Vitest suites
  for agent controls, editor preferences, and sharing. All currently passing tests
  must remain green.
- **New/updated backend tests (pytest):** the reserved-name and control-char upload
  cases in `test_files_api.py` (Issue 47), plus the tightened traversal assertion
  (Issue 41). These use the existing test client and in-memory/local storage
  fixtures — no real network or external storage.
- **New/updated frontend tests (Vitest):** the `useEditorPreferences` hook mapping
  test (Issue 248). The agent-composer spinner/tooltip and share-dialog
  inline-error/skeleton changes should be covered by (or kept green against)
  existing component tests; add a focused assertion only if cheap and within scope
  (the relevant test files are mostly out of scope, so prefer not to add new test
  files outside §2).
- **Performance/budget note:** all additions are pure unit/integration/component
  tests with mocked or local fixtures; the full suite stays under 2 minutes.

## 6. Definition of Done

- [ ] All nine issues in §3 fixed (41, 47, 72, 74, 184, 187, 141, 248, 133).
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; pre-existing tests still
      green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff for Python; ESLint/Prettier + strict TS
      for frontend).
- [ ] Only files listed in §2 were modified.
- [ ] No Overleaf code copied.
