# Spec 88 — Fix-pack: e2e flows, PDF zoom, diff unit test & Docker build (requirements)

## 1. Summary

This fix-pack closes nine confirmed issues, found by two independent reviewers,
that center on **missing Playwright e2e flows** plus a few adjacent gaps. The
MAJORs are: the spec-18 read-only + in-editor font-size e2e flow, the spec-19
REST-autosave (Saving…→Saved→reload) e2e flow, the spec-54 collab-presence
assertion (journey 5 / AC6), and the spec-56 frontend Dockerfile lockfile-path
break. The minors: a spec-54 `ShareDialog` page object + UI invite step, a
spec-16 dashboard open→URL→back e2e step, a debounced PDF zoom (spec 24), an
oversized-doc unit test (spec 43), and a resolver-omission note in ADR-0056
(spec 56). For every e2e item, the fix is to **add** the missing Playwright
test(s) per the source spec's §8; **real-compile and LLM parts must be stubbed**
to keep the suite under 2 minutes.

## 2. Files in scope

Edit **only** these files (the exact `payload.files` set). Do not touch any file
outside this list — other fix-packs may be running in parallel on other files.

- `backend/src/inkstave/agent/diffs/__init__.py`
- `backend/tests/unit/test_agent_diffs_unit.py`
- `docs/adr/0056-docker-production.md`
- `frontend/Dockerfile`
- `frontend/e2e/collab.spec.ts`
- `frontend/e2e/editor.spec.ts`
- `frontend/e2e/project.spec.ts`
- `frontend/e2e/support/pages.ts`
- `frontend/src/features/pdf-preview/PdfViewer.tsx`
- `frontend/src/features/pdf-preview/hooks/usePdfViewport.ts`

Restrict edits: add new e2e specs/steps and page objects only inside the
in-scope e2e files (`collab.spec.ts`, `editor.spec.ts`, `project.spec.ts`,
`support/pages.ts`). The `agent/diffs/__init__.py` change is limited to
extracting/exposing the oversized-doc check for unit testing (issue 174); the
PDF zoom change is limited to `PdfViewer.tsx` + `usePdfViewport.ts`.

## 3. Issues to fix

### Issue 63 — spec-18 read-only + in-editor font-size e2e missing (MAJOR)

- **Source spec:** 18-editor-ui-codemirror
- **Severity:** major
- **File(s):** `frontend/e2e/editor.spec.ts`
- **Problem:** Spec 18 §8 (305–308) requires one e2e flow: open a seeded project →
  click `main.tex` → editor shows content with highlighting and line numbers →
  attempt to type (no change, **read-only**) → open settings, increase font size
  → observe it applied. The existing `editor.spec.ts` (line 10) covers
  create/edit/reload persistence (a spec-19 *editable* flow). `grep` finds no
  read-only / font-size / line-number / highlight assertions.
- **Fix to apply:** Add a short Playwright spec that opens a seeded **read-only**
  document, asserts line numbers and syntax highlighting render (e.g. CodeMirror
  gutter line numbers + token spans), asserts typing does **not** change content
  (read-only), opens the **in-editor settings popover**, increases the font size,
  and asserts the applied computed `font-size` on the editor changed. Use the
  existing seeding/login fixtures and `EditorPage` page object. Stub any compile.

### Issue 68 — spec-19 REST-autosave e2e flow missing (MAJOR)

- **Source spec:** 19-document-autosave-rest
- **Severity:** major
- **File(s):** `frontend/e2e/editor.spec.ts`, `frontend/e2e/support/pages.ts`
- **Problem:** Spec 19 §8 requires the flow: open a seeded doc → edit it → see
  "Saving…" then "Saved" → reload → the edit persisted. The current
  `editor.spec.ts` (lines 4–6) runs in CRDT/collab mode and asserts persistence
  by reload rather than a REST "Saved" badge. The `savedBadge()` locator exists
  in `pages.ts:119` but is never invoked in any e2e spec.
- **Fix to apply:** Add an e2e test exercising the **REST autosave** path: edit a
  seeded doc (in non-collab/REST mode if the app supports a mode toggle/route;
  otherwise drive the autosave-badge UI), assert the `savedBadge()` shows
  "Saving…" then "Saved" (use the existing `savedBadge()` page object — wire it up
  if it needs a small helper), then reload and verify the edit persisted. Keep the
  flow short and stub compile. If the app cannot run a pure-REST mode in e2e,
  implement the minimal hook needed within the in-scope e2e files to surface and
  assert the saved-badge transitions.

### Issue 227 — collab presence assertion missing (journey 5 / AC6) (MAJOR)

- **Source spec:** 54-e2e-suite
- **Severity:** major
- **File(s):** `frontend/e2e/collab.spec.ts`
- **Problem:** Spec 54 AC6 / journey 5 (§5.3) require both users to **see each
  other's presence** (cursor / online list). `collab.spec.ts:62–64` explicitly
  skips presence rendering, deferring it to the spec-32 Vitest unit suite; no
  online-indicator / avatar / remote-cursor selector exists in the test.
- **Fix to apply:** Add a presence assertion to the collab journey: after both
  contexts join the same project, assert in each context that the **other user's
  presence** is visible — an online indicator / avatar in the presence list and/or
  a remote-cursor caret in the editor. Use stable selectors/data-testids from the
  presence UI (spec 32 components). Replace the deferral comment with the real
  assertion. Keep the two-context setup already used in the spec.

### Issue 235 — frontend Dockerfile copies the lockfile from the wrong path (MAJOR)

- **Source spec:** 56-docker-production
- **Severity:** major
- **File(s):** `frontend/Dockerfile`, `docs/adr/0056-docker-production.md`
- **Problem:** The repo uses a pnpm **workspace**: `pnpm-workspace.yaml` lists
  `frontend`, so the lockfile (`pnpm-lock.yaml`) lives at the **repo root**, not in
  `frontend/`. `frontend/Dockerfile:19`
  `COPY frontend/package.json frontend/pnpm-lock.yaml* ./` — the glob silently
  skips the non-existent `frontend/pnpm-lock.yaml`, so line 20
  `pnpm install --frozen-lockfile` runs with **no lockfile** in the image and
  aborts. The frontend image cannot be built from a clean checkout, breaking
  spec 56 AC2.
- **Fix to apply:** Make the frozen install find the workspace root lockfile.
  Either (a) copy the workspace root lockfile + workspace manifest before install
  (`COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./` then
  `COPY frontend/package.json frontend/`) and run the frozen install at the
  workspace root, or (b) restructure the build so `--frozen-lockfile` resolves the
  root lockfile. Verify the documented build command succeeds from a clean
  checkout. Update ADR-0056's "Known follow-ups" so it no longer claims the frozen
  install will fail.

### Issue 228 — ShareDialog page object + UI invite step missing (MINOR)

- **Source spec:** 54-e2e-suite
- **Severity:** minor
- **File(s):** `frontend/e2e/support/pages.ts`, `frontend/e2e/collab.spec.ts`
- **Problem:** Spec §5.2 (97) lists "share dialog" among the required page
  objects, but `pages.ts` exports `LoginPage`, `DashboardPage`, `EditorPage`,
  `PreviewPanel`, `AgentPanel`, `DiffReview`, `HistoryPanel` — no `ShareDialog`.
  The invite flow in `collab.spec.ts:35–36` is done via `apiA.invite()` /
  `apiB.acceptInvite()` (pure API), so `ShareDialog.tsx` is never exercised
  through the browser.
- **Fix to apply:** Add a `ShareDialog` page object to `pages.ts` (open the Share
  modal, fill the invite email, choose a role, submit). Add an e2e step in
  `collab.spec.ts` that opens the Share modal **through the UI** and invites a
  collaborator, exercising `ShareDialog.tsx` in the browser. The invitee can still
  accept via API if needed to keep the flow short, but the **invite** must go
  through the UI dialog.

### Issue 49 — dashboard open→URL→back e2e step missing (MINOR)

- **Source spec:** 16-project-dashboard-ui
- **Severity:** minor
- **File(s):** `frontend/e2e/project.spec.ts`
- **Problem:** Spec 16 §8 (337–340) mandates a single flow including "open it (URL
  becomes `/projects/:id`) → go back". `project.spec.ts:10–28` does
  create → rename → reload → delete, with no `dashboard.open()` call and no URL
  assertion, so AC §10 ("clicking a project name navigates to
  `/projects/:projectId` and the editor shell renders") is not e2e-covered via the
  dashboard.
- **Fix to apply:** In `project.spec.ts`, after rename, call
  `dashboard.open(renamed)` (the existing `DashboardPage.open` at `pages.ts:67`),
  assert `page.url()` matches `/projects/<id>`, assert the editor shell renders
  without error, then go back to `/projects` before the delete step. Keep the
  existing create/rename/delete coverage intact.

### Issue 89 — PDF zoom re-renders not debounced (MINOR)

- **Source spec:** 24-pdf-preview-ui
- **Severity:** minor
- **File(s):** `frontend/src/features/pdf-preview/PdfViewer.tsx`,
  `frontend/src/features/pdf-preview/hooks/usePdfViewport.ts`
- **Problem:** Spec 24 §5.3.4 (137) requires "debounce zoom re-renders".
  `PdfViewer.tsx:46–64` re-renders every page canvas on every `scale` change via a
  `useEffect` with `scale` in its deps, with no debounce/throttle (the word
  "debounce" appears nowhere). The effect does cancel the prior in-flight task, so
  "many concurrent tasks" is overstated, but the spec-mandated debounce is absent.
- **Fix to apply:** Debounce/throttle scale changes so rapid zoom clicks coalesce
  into a single render. Preferred: debounce the `scale` value in
  `usePdfViewport.ts` before pushing it to the viewport (expose a debounced scale),
  or wrap the render effect in `PdfViewer.tsx` with a short debounce. Keep the
  existing in-flight cancellation. Add/extend a unit test if one exists for the
  hook; otherwise verify behaviourally.

### Issue 174 — oversized-doc handling unit test missing (AC9) (MINOR)

- **Source spec:** 43-agent-diff-generation
- **Severity:** minor
- **File(s):** `backend/tests/unit/test_agent_diffs_unit.py`,
  `backend/src/inkstave/agent/diffs/__init__.py`
- **Problem:** Spec §8 lists "Oversized doc handling (AC 9)" under the **Unit**
  pytest bullet. No unit test exists; it is only covered by the integration test
  `test_oversized_doc_is_skipped`. The oversized check is inlined in
  `materialize_diffs` (`diffs/__init__.py:75`) rather than a pure helper, making a
  pure unit test impossible without async DB infrastructure.
- **Fix to apply:** Extract the oversized-doc threshold check into a small pure
  helper in `diffs/__init__.py` (e.g. `_is_oversized(content, max_doc_chars)` or
  similar), used by `materialize_diffs`, and add a unit test in
  `test_agent_diffs_unit.py` that exercises the `> max_doc_chars` skip branch
  directly (no DB). Keep behaviour identical and the integration test still green.

### Issue 237 — resolver omission not documented in ADR-0056 (MINOR)

- **Source spec:** 56-docker-production
- **Severity:** minor
- **File(s):** `docs/adr/0056-docker-production.md`
- **Problem:** Spec §5.5 (189) says "use variables + a resolver only if needed for
  restart resilience (document the choice)". The implementation omits a resolver
  directive (acceptable), but the ADR does not record **why** it was omitted, as
  the spec requires. `grep 'resolver'` returns nothing.
- **Fix to apply:** Add a sentence to ADR-0056 stating the resolver directive was
  deliberately omitted and why (e.g. static upstream service names within the
  compose network make a resolver unnecessary for the current topology).

## 4. Acceptance criteria

1. A Playwright spec opens a seeded read-only doc, asserts line numbers +
   highlighting render, asserts typing does not change content, opens the
   in-editor settings popover, increases font size, and asserts the applied
   computed font-size changed (issue 63).
2. A Playwright spec edits a doc, asserts `savedBadge()` shows "Saving…" then
   "Saved", reloads, and verifies persistence (issue 68).
3. The collab journey asserts each context sees the other user's presence
   (online indicator/avatar and/or remote-cursor caret) (issue 227).
4. The frontend Docker image builds from a clean checkout: `--frozen-lockfile`
   resolves the workspace root lockfile; ADR-0056 no longer claims the frozen
   install will fail (issue 235).
5. `pages.ts` exports a `ShareDialog` page object and `collab.spec.ts` invites a
   collaborator through the Share modal UI (issue 228).
6. `project.spec.ts` opens a project via the dashboard, asserts the URL becomes
   `/projects/<id>` and the editor shell renders, then goes back before delete
   (issue 49).
7. PDF zoom scale changes are debounced/throttled so rapid zoom clicks coalesce
   into one render (issue 89).
8. A pure unit test exercises the oversized-doc skip branch via an extracted
   helper in `diffs/__init__.py` (issue 174).
9. ADR-0056 records that the resolver directive was omitted and why (issue 237).

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Real Tectonic compiles and real LLM calls MUST be stubbed in these tests.

- **Existing green:** Run backend pytest, frontend Vitest, and the Playwright e2e
  suite before and after; keep green.
- **New e2e (Playwright):**
  - Read-only + in-editor font-size flow (issue 63), in `editor.spec.ts`.
  - REST-autosave Saving→Saved→reload flow (issue 68), in `editor.spec.ts`,
    using `savedBadge()` from `pages.ts`.
  - Collab presence assertion (issue 227), in `collab.spec.ts`.
  - `ShareDialog` page object + UI invite step (issue 228), in `pages.ts` /
    `collab.spec.ts`.
  - Dashboard open→URL→back step (issue 49), in `project.spec.ts`.
  - All e2e flows reuse existing seeding/login fixtures and **stub real
    compile/LLM** so the suite stays under budget.
- **New unit (pytest):** Oversized-doc skip-branch test against the extracted
  helper (issue 174) in `test_agent_diffs_unit.py`.
- **Frontend unit (Vitest):** Debounce behaviour for PDF zoom (issue 89), if a
  hook test harness exists; otherwise verify behaviourally and keep render tests
  green.
- **Docs/build:** Docker lockfile fix (issue 235) verified by a clean-checkout
  build of the frontend image (or by confirming the lockfile is copied before the
  frozen install); ADR notes (235, 237) verified by inspection.
- **Performance/budget note:** e2e flows are short and stub compile/LLM; the
  oversized-doc unit test is pure (no DB). The full suite must stay under
  2 minutes.

## 6. Definition of Done

- [ ] All nine issues (63, 68, 227, 235, 228, 49, 89, 174, 237) addressed as
      described in §3.
- [ ] All acceptance criteria in §4 pass.
- [ ] New e2e/unit tests in §5 written and green; existing tests stay green.
- [ ] Full suite (incl. e2e) runs in < 2 minutes; no real compile/LLM in tests.
- [ ] Lint/format/type-check clean (ESLint/Prettier/`tsc`; `ruff`/`mypy`).
- [ ] Only files listed in §2 were modified.
- [ ] No Overleaf code copied.
