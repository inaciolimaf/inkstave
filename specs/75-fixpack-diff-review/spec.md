# Spec 75 — Fix-pack: diff-review UI hardening, auth & contract alignment (requirements)

## 1. Summary

This fix-pack applies **9 confirmed issues** drawn from specs
`06-user-model-registration`, `18-editor-ui-codemirror`, `34-access-control`,
`42-agent-tools`, and `47-diff-review-ui`. Each was verified by two independent
reviewers.

**Severity breakdown (adjusted):**

- **Major:** 3 — all in the diff-review UI:
  - #191 confirm before discarding pending decisions on accidental dismiss;
  - #192 `FilePreview` must use a read-only **CodeMirror**, not a raw `<pre>`;
  - #190 render a distinct **apply-error** state and stop the false success toast.
- **Minor:** 5 — #199 `DiffProposal.createdAt` missing; #193 `isNewFile` /
  `isDeletion` fields + labels missing; #65 ADR-0018 contradicts shipped
  vim/emacs keymaps; #168 `ToolContext` shape vs spec §5.2.1; #136
  `AuthorizationService` shape + caching query-count test.
- **Nit:** 1 — #17 integration `test_register` parametrize missing three cases.

The headline work is the three MAJOR diff-review UI fixes; the rest are
type/contract/documentation/test alignments.

## 2. Files in scope

Edit **only** these files (exact payload set):

- `backend/src/inkstave/agent/tools/base.py`
- `backend/src/inkstave/authorization/capabilities.py`
- `backend/src/inkstave/authorization/service.py`
- `backend/tests/integration/test_register.py`
- `docs/adr/0018-latex-language.md`
- `frontend/src/features/diff-review/DiffReviewDialog.tsx`
- `frontend/src/features/diff-review/types.ts`
- `frontend/src/features/diff-review/useDiffReview.ts`
- `frontend/src/features/editor/keymap-extension.ts`

> **Restrict-edits note:** Do not modify any file outside this list. In
> particular, the read-only CodeMirror fix (#192) must **reuse** the editor's
> existing read-only configuration via imports — do **not** edit the editor
> components themselves; if a tiny read-only CodeMirror wrapper is needed, add it
> **inside** `DiffReviewDialog.tsx` (or co-locate it in the diff-review folder
> only if absolutely necessary — but the payload lists only `DiffReviewDialog.tsx`
> for the UI, so prefer an in-file component). `keymap-extension.ts` is listed
> only so the ADR (#65) can be reconciled against the real imports; no behaviour
> change is required there.

## 3. Issues to fix

### Issue #191 — Confirm before discarding pending decisions (MAJOR)

- **Source spec:** 47-diff-review-ui (§5.4).
- **File:** `frontend/src/features/diff-review/DiffReviewDialog.tsx`.
- **Problem:** §5.4 requires the dialog to "not lose unsaved decisions on
  accidental dismiss — confirm before discarding pending decisions". The
  `<Dialog open={open} onOpenChange={onOpenChange}>` (verified, line 183) passes
  `onOpenChange` straight through with **no** `onInteractOutside` /
  `onEscapeKeyDown` intercept and no discard-confirmation. (The `preventDefault`
  at line 269 is inside the Apply confirmation, not a dismiss guard.)
- **Fix to apply:**
  1. Determine whether there are **pending unsaved decisions** — i.e. the
     proposal is loaded, the user has interacted, and the changes have **not yet
     been applied** (`applyPhase !== "applied"`). A simple, robust signal: the
     proposal has files/hunks and `applyPhase` is `idle`/`confirming` and the
     user has toggled at least one hunk away from its loaded default (or simply:
     there are accepted hunks not yet applied). Use a clear predicate; the safe
     default is "there is at least one reviewable hunk and nothing has been
     applied yet".
  2. Intercept dismissal: on `DialogContent`, add `onInteractOutside` and
     `onEscapeKeyDown` handlers that `preventDefault()` when pending decisions
     exist and instead open a **discard-confirmation** `AlertDialog`
     ("Discard your review? Your accept/reject choices will be lost.").
  3. Wrap `onOpenChange`: when called with `false` while pending decisions exist,
     do **not** close immediately — show the discard confirmation first. On
     confirm, call `onOpenChange(false)`; on cancel, keep the dialog open.
  4. When there are no pending decisions (nothing to lose, or already applied),
     dismiss passes through unchanged.
  Reuse the existing shadcn `AlertDialog` primitives already imported in the
  file.

### Issue #192 — FilePreview must use read-only CodeMirror, not `<pre>` (MAJOR)

- **Source spec:** 47-diff-review-ui (§5.4 and §3).
- **File:** `frontend/src/features/diff-review/DiffReviewDialog.tsx`.
- **Problem:** §5.4 says `FilePreview` is "CodeMirror read-only" and §3 says
  "not a raw `<pre>`". The preview is currently rendered (verified, line 141) as
  `<pre className="...">{previewText}</pre>`.
- **Fix to apply:** Replace the `<pre>` block in `FileSection` with a
  **read-only CodeMirror 6** instance rendering `previewText`:
  - Mount a CodeMirror `EditorView` (or use the project's existing CodeMirror
    React wrapper if one is already importable without editing other files) into
    a container `div`, configured read-only / non-editable
    (`EditorState.readOnly.of(true)` and `EditorView.editable.of(false)`), with
    line wrapping consistent with the rest of the UI and a `max-h-72` scroll
    container matching the prior styling.
  - Update its document when `previewText` changes (dispatch a full-replace
    transaction), and destroy the view on unmount.
  - Keep it self-contained inside `DiffReviewDialog.tsx` (a small
    `ReadonlyCodePreview` component in the same file). Do **not** edit the editor
    feature files; import only the CodeMirror packages already in use
    (`@codemirror/state`, `@codemirror/view`). Preserve the read-only and
    accessible behaviour (no editing, focusable for scroll/selection).

### Issue #190 — Apply-error state never rendered; false success toast (MAJOR)

- **Source spec:** 47-diff-review-ui (§5.4 states list; AC9).
- **Files:** `frontend/src/features/diff-review/DiffReviewDialog.tsx`,
  `frontend/src/features/diff-review/useDiffReview.ts`.
- **Problem:** `useDiffReview` sets `applyPhase = "error"` when any per-file
  result has an `error` (verified, line 147), but the dialog's render chain
  (loading → isError → empty → `applyPhase === "applied"` → file list) has **no
  branch for `"error"`** — it falls through and re-renders the file list with no
  banner. Worse, the Apply `AlertDialogAction` `onClick` (verified, line 270)
  **unconditionally** calls `toast.success("Changes applied to your document.")`
  even when the apply errored. This violates AC9 ("reports applied files/hunks
  and any blocked/errored items") and the §5.4 "error" state.
- **Fix to apply:**
  1. In `DiffReviewDialog.tsx`, add an `applyPhase === "error"` branch in the
     main content area that renders the **results summary** (reuse the same
     per-`res` rendering as the `"applied"` branch, including `res.error`) inside
     a **distinct destructive `Alert`** ("Some changes could not be applied").
     Make this branch sit alongside/just before the `"applied"` branch so error
     takes precedence.
  2. Gate the toast on the resulting phase: after `await onApply()`, show
     `toast.success(...)` only when `r.applyPhase !== "error"`, and
     `toast.error("Some changes couldn't be applied.")` otherwise. Read the phase
     **after** apply resolves (e.g. have `apply()` return the outcome, or branch
     on the result count of errored items), not the stale closure value.
  3. Do not change the success path behaviour when there are no errors.

### Issue #199 — `DiffProposal.createdAt` missing (minor)

- **Source spec:** 47-diff-review-ui (§2.1).
- **File:** `frontend/src/features/diff-review/types.ts`.
- **Problem:** §2.1 declares `interface DiffProposal { id; projectId; sessionId;
  files; createdAt: string }`. The frontend type (verified, lines 27–32) omits
  `createdAt`.
- **Fix to apply:** Add `createdAt: string` to `DiffProposal` in `types.ts`, and
  map it from the wire in the proposal loader if the field is present. (If the
  loader lives outside this file set, only add the type field and ensure the
  mapping site — `api.ts`? — is **not** in scope; if mapping cannot be done
  without an out-of-scope edit, add the field to the type and leave a `// mapped
  from wire createdAt` note; do not edit out-of-scope files.)

### Issue #193 — `isNewFile` / `isDeletion` fields + labels missing (minor)

- **Source spec:** 47-diff-review-ui (§2.1; §5.4).
- **Files:** `frontend/src/features/diff-review/types.ts`,
  `frontend/src/features/diff-review/DiffReviewDialog.tsx`.
- **Problem:** §2.1 `ProposedFileDiff` includes `isNewFile?: boolean` and
  `isDeletion?: boolean`, and §5.4 requires "New-file / deletion files are
  labelled". Neither field exists (verified, types.ts lines 20–25) and
  `FileSection` renders no such label.
- **Fix to apply:**
  1. Add optional `isNewFile?: boolean` and `isDeletion?: boolean` to
     `ProposedFileDiff` in `types.ts`.
  2. In `FileSection` (`DiffReviewDialog.tsx`), render a shadcn `Badge` next to
     `file.path`: "New file" when `file.isNewFile`, "Deleted" when
     `file.isDeletion`. (Reuse the already-imported `Badge`.)

### Issue #65 — ADR-0018 contradicts shipped vim/emacs keymaps (minor)

- **Source spec:** 18-editor-ui-codemirror.
- **Files:** `docs/adr/0018-latex-language.md`,
  `frontend/src/features/editor/keymap-extension.ts` (reference only).
- **Problem:** ADR-0018 §4 states vim/emacs are "intentionally omitted to avoid
  extra dependencies", but `keymap-extension.ts` (verified, lines 4–5) imports
  and fully supports both via `@replit/codemirror-vim` and
  `@replit/codemirror-emacs` (both shipped in `package.json`). The ADR's "New
  deps" list omits these packages.
- **Fix to apply:** Update ADR-0018: remove the "intentionally omitted" claim,
  state that vim/emacs keymaps **do** ship, and add `@replit/codemirror-vim` and
  `@replit/codemirror-emacs` (both MIT) to the "Consequences — New deps" list. Do
  not change `keymap-extension.ts` behaviour; it is in scope only to confirm the
  truth the ADR must reflect.

### Issue #168 — `ToolContext` shape vs spec §5.2.1 (minor)

- **Source spec:** 42-agent-tools (§5.2.1).
- **File:** `backend/src/inkstave/agent/tools/base.py`.
- **Problem:** §5.2.1 defines `ToolContext` as a Pydantic `BaseModel`
  (`arbitrary_types_allowed=True`) with explicit `tree_service: FileTreeService`
  and `doc_service: DocumentService` fields. The implementation (verified, lines
  32–43) is a `@dataclass` holding `db: AsyncSession` (plus
  `project_id`/`user_id`/`settings`/`staged_edits`) and no service fields;
  services are called as module-level functions.
- **Fix to apply:** Choose the **lower-risk** of these, faithful to the spec
  intent, without editing out-of-scope files:
  - **Preferred:** Document the deliberate deviation — add a clear docstring/
    comment on `ToolContext` in `base.py` recording that the dataclass +
    module-level service functions are the **chosen design** (DI via `db`),
    explicitly noting it diverges from the §5.2.1 `BaseModel` shape and why.
  - If service fields can be added **without** importing out-of-scope modules in
    a way that breaks the file-disjointness, you may add them; but if that pulls
    in edits to other files, **do not** — use the documented-deviation option.
  No behavioural change to callers.

### Issue #136 — `AuthorizationService` shape + caching query-count test (minor)

- **Source spec:** 34-access-control (§5.2; §8).
- **Files:** `backend/src/inkstave/authorization/service.py`,
  `backend/src/inkstave/authorization/capabilities.py`.
- **Problem:** §5.2 mandates a `class AuthorizationService` with `get_role`,
  `get_capabilities`, `authorize` (raising `ForbiddenError`/`NotFoundError`),
  and `can`. The implementation uses standalone functions (`role_for`,
  `capabilities_for`) with the gate in `dependencies.py::require_capability`
  (out of scope). Error semantics are already integration-tested, but §8's
  "request-scoped caching does one membership lookup" has no explicit
  query-count assertion.
- **Fix to apply:** Do the **minimal, in-scope** alignment:
  - In `service.py` / `capabilities.py`, add a thin `AuthorizationService` class
    (or clearly-documented module facade) exposing `get_role`,
    `get_capabilities`, `authorize`, and `can` that **delegate** to the existing
    `role_for` / `capabilities_for` and raise the existing
    `ForbiddenError`/`NotFoundError` semantics — **without** changing the
    request-scoped caching that lives in `dependencies.py` (out of scope; do not
    edit it). If the `authorize`/`can` methods would require the request-scoped
    cache that lives out of scope, implement them against the in-scope functions
    and document that the production gate remains `require_capability`.
  - **Alternatively**, if introducing the class risks behaviour drift, instead
    add a precise docstring in `service.py` recording the function-based design
    as a deliberate, reviewed deviation from the §5.2 class shape.
  - The caching query-count test ("a single endpoint authorizing the same
    project twice issues only one membership lookup") belongs to an integration
    test file **not in this fix-pack's scope**; therefore, **note this gap in the
    `service.py` docstring** and do not add the test here. (Out-of-scope test
    files must not be created/edited by this pack.)

### Issue #17 — `test_register` integration parametrize incomplete (nit)

- **Source spec:** 06-user-model-registration (AC4).
- **File:** `backend/tests/integration/test_register.py`.
- **Problem:** `test_register_validation_errors` (verified, parametrize ~lines
  67–73) covers bad-email, too-short password, no-digit password, and empty
  display name, but **omits** "no letter in password", "too long password (>72
  chars)", and "password equal to / containing the email local-part". AC4
  enumerates all of these at the API (422) level. (They are covered at the unit
  level but not integration.)
- **Fix to apply:** Add three cases to the integration parametrize list, each
  asserting **HTTP 422**:
  - a password with **no letter** (e.g. all digits, length ≥ 8);
  - a password **longer than 72** characters;
  - a password **equal to or containing the email local-part**.
  Match the existing parametrize/assertion style in the file.

## 4. Acceptance criteria

1. **Discard guard (#191):** Pressing Escape / clicking outside the diff-review
   dialog while there are pending (unapplied) decisions opens a discard
   confirmation; confirming closes the dialog, cancelling keeps it open. With no
   pending decisions (or already applied), dismissal passes through.
2. **CodeMirror preview (#192):** Toggling "Preview" renders the file content in
   a **read-only CodeMirror** instance (not a `<pre>`); the content is not
   editable and updates when the underlying preview text changes.
3. **Apply-error state (#190):** When an apply produces any per-file error, the
   dialog shows a distinct destructive error summary listing the errored items,
   and a `toast.error` (not `toast.success`) is shown. The pure-success path
   still shows the success toast and the "applied" summary.
4. **Accept-all / reject-all (test, #190/§5.4 surface):** A test exercises the
   "Accept all" and "Reject all" controls and asserts the accepted-hunk count
   updates accordingly (and that apply respects those decisions).
5. **`createdAt` (#199):** `DiffProposal` includes `createdAt: string`.
6. **New/deleted labels (#193):** `ProposedFileDiff` has optional `isNewFile` /
   `isDeletion`; `FileSection` shows a "New file" / "Deleted" badge when set.
7. **ADR-0018 (#65):** The ADR no longer claims vim/emacs are omitted and lists
   both `@replit` packages under New deps.
8. **`ToolContext` (#168):** `base.py` either matches §5.2.1's service-field
   shape or carries a clear documented deviation; callers unchanged.
9. **`AuthorizationService` (#136):** `service.py`/`capabilities.py` provide the
   named `AuthorizationService` facade (or a documented deviation), delegating to
   existing functions with unchanged semantics; the caching query-count gap is
   noted in-code (test deferred — out of scope).
10. **Register validation (#17):** The integration parametrize includes
    no-letter, >72-char, and local-part-in-password cases, each asserting 422.

## 5. Test plan

> The whole suite must stay under 2 minutes.

- **Existing green:** Run Vitest and pytest before/after; keep green.
- **Vitest (frontend), in the diff-review test file(s):**
  - **Discard guard (#191/AC1):** simulate Escape/outside-interaction with
    pending decisions → discard confirmation appears; confirm → `onOpenChange(false)`
    fired; cancel → dialog stays open. With no pending decisions → closes
    directly.
  - **CodeMirror preview (#192/AC2):** toggle Preview → a read-only CodeMirror
    (not `<pre>`) is present; assert the rendered content and non-editability.
  - **Apply-error (#190/AC3):** stub the `DocumentBridge.applyContent` to throw
    for one file → after apply, the error summary renders and `toast.error` is
    called; success path → `toast.success` and applied summary.
  - **Accept-all / reject-all (#AC4):** click "Accept all" / "Reject all" and
    assert the accepted count and the apply plan reflect the toggles.
  - **Types (#199/#193):** type-level/render assertions for `createdAt` and the
    new/deleted badges.
- **pytest (backend):**
  - **Register (#17/AC10):** the three new parametrized cases each return 422.
  - **AuthorizationService / ToolContext (#136/#168):** if a facade/class is
    added, a small unit test that `get_role`/`get_capabilities`/`authorize`/`can`
    delegate correctly and raise the right errors; otherwise no new test (the
    documented-deviation option), keeping existing auth tests green.
- **Performance/budget note:** All new tests are in-process React/unit tests and
  fast unit/integration pytest cases; no LaTeX/LLM/real network. No real timers.

## 6. Definition of Done

- [ ] All 9 issues in §3 applied; no files outside §2 touched.
- [ ] The 3 MAJOR diff-review UI fixes (#191, #192, #190) are implemented and
      tested, including the accept-all/reject-all and apply-error tests.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; full suite < 2 minutes.
- [ ] Lint/format/type-check clean (ruff + mypy/pyright; ESLint + Prettier,
      strict TS).
- [ ] Preview uses read-only CodeMirror; no raw `<pre>` remains for the preview.
- [ ] No false success toast on apply errors.
- [ ] No unrelated refactors; no Overleaf code copied; no out-of-scope edits.
