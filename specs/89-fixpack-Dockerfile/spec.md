# Spec 89 — Fix-pack: Docker build break + refactor-docs & test-coverage gaps (requirements)

## 1. Summary

This fix-pack bundles nine validation-confirmed issues whose files are disjoint
from every other fix-pack, so it can run in parallel. The issues are
documentation and test-coverage gaps inherited from specs 16, 26, 34, 46, 47, 56
and 60: the backend Dockerfile is missing a note about deliberately omitted
Postgres OS packages; the refactor-final CHANGELOG omits per-area scan records,
the structured findings format, and empirical flakiness evidence; the agent/diff
E2E test omits several mandated assertions; the rename-dialog has no unit test;
the viewer-update integration test never proves "no broadcast"; and the synctex
API client sits in the wrong directory.

> **Note:** the frontend Docker build break (confirmed issue **235**) is owned by
> spec **88**, not this pack — spec 89 does **not** touch any frontend Docker
> files (`frontend/Dockerfile`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`).

## 2. Files in scope

Edit **only** these files (the payload set). Do not touch anything outside this
list; other fix-packs run concurrently on other files. In particular, do **not**
touch `frontend/Dockerfile`, `pnpm-lock.yaml`, or `pnpm-workspace.yaml` — the
frontend Docker fix is spec 88's.

Payload files:

- `backend/Dockerfile`
- `backend/tests/integration/test_collab_ws_access.py`
- `docs/CHANGELOG.md`
- `frontend/e2e/agent.spec.ts`
- `frontend/src/features/pdf-preview/synctex.ts`
- `frontend/src/features/projects/project-dialogs.test.tsx`

Restrict-edits note: if a fix can be made without touching one of the above, do
not touch it. Issue **97** (synctex client location) requires moving a file; the
move's source (`frontend/src/features/pdf-preview/synctex.ts`) and the new
location `frontend/src/lib/api/synctex.ts` are both considered in-scope for that
single relocation, plus the import sites that reference it (kept minimal — see
the issue note). If relocating would force edits to files outside this pack's
scope, prefer the documentation-only resolution described under issue **97**.

## 3. Issues to fix

### Issue 236 — Backend Dockerfile: undocumented postgresql-dev / libpq omission

- **ID:** 236
- **Source spec:** 56-docker-production
- **Severity:** minor (adjusted: minor)
- **File(s):** `backend/Dockerfile`
- **Problem:** Spec 56 §5.2 Stage 1 lists `postgresql-dev` in the builder and
  §5.2 Stage 3 lists `libpq` in the runtime OS packages. Both are absent
  (builder line 15: `RUN apk add --no-cache build-base libffi-dev`; runtime line
  38: `RUN apk add --no-cache ca-certificates fontconfig ttf-freefont
  tectonic`). The omission is functionally correct — Inkstave uses `asyncpg`,
  which implements the Postgres wire protocol natively and does not link
  `libpq` — but the deliberate deviation from the spec text is not noted in the
  Dockerfile or ADR.
- **Fix to apply:** Add a short comment in `backend/Dockerfile` (near the builder
  `apk add` and/or the runtime `apk add`) explaining that `postgresql-dev`
  (builder) and `libpq` (runtime) are intentionally omitted because `asyncpg`
  speaks the Postgres wire protocol natively and needs no `libpq`. This is a
  comment-only change; do not add the packages. (You may instead/also note it in
  `docs/adr/0056`, but `docs/adr/0056` is **out of scope** for this pack — keep
  the note inside `backend/Dockerfile`.)

### Issue 251 — Refactor CHANGELOG: missing per-area scan records (areas 3/4/5)

- **ID:** 251
- **Source spec:** 60-refactor-final
- **Severity:** major (adjusted: minor)
- **File(s):** `docs/CHANGELOG.md`
- **Problem:** Spec 60 §5.1 requires enumerating findings for **all nine**
  scanned areas. `docs/CHANGELOG.md` records nothing — not even "none found" —
  for area 3 (Collaboration/CRDT), area 4 (Compilation), and area 5 (AI agent).
  Prior refactor docs explicitly recorded "none found" when an area was clean
  (e.g. `docs/refactors/05-foundations.md` F-010: "none found"). The CHANGELOG's
  "focused on newest code (56–59)" rationale does not substitute for the
  per-area scan record.
- **Fix to apply:** Add explicit per-area scan records to `docs/CHANGELOG.md` for
  Collaboration/CRDT, Compilation, and AI agent. Where the reviewers found
  nothing, record an explicit "none found" entry (matching the prior convention).
  These records should make it unambiguous that all nine §5.1 areas were scanned.
  (See issue 250 for the structured format these records should use.)

### Issue 250 — Refactor CHANGELOG: findings not in the required structured format

- **ID:** 250
- **Source spec:** 60-refactor-final
- **Severity:** major (adjusted: minor)
- **File(s):** `docs/CHANGELOG.md`
- **Problem:** Spec 60 §5.1 mandates that **each finding** record: `id`, `area`,
  `description`, `severity (low/med/high)`, `risk-of-fix`, `value-of-fix`,
  `decision (apply/skip)`, and (if applied) a change reference / (if skipped) the
  rationale. The CHANGELOG uses narrative prose with inline severities — no
  explicit `id`, no `area` label, no separate `risk-of-fix` / `value-of-fix`
  fields. All prior refactor passes used a structured findings table.
- **Fix to apply:** Reformat the spec-60 findings in `docs/CHANGELOG.md` as a
  structured findings table (or clearly-labelled list) with columns:
  `id | area | description | severity (low/med/high) | risk-of-fix | value-of-fix
  | decision (apply/skip) | change-ref / rationale`, matching §5.1 and the prior
  refactor-pass convention (see `docs/refactors/05-foundations.md`). Fold the
  per-area "none found" records from issue 251 into this same table so the two
  fixes are consistent. Preserve the existing applied/skipped information — only
  restructure it into the mandated format.

### Issue 253 — Refactor CHANGELOG: flakiness check lacks empirical evidence

- **ID:** 253
- **Source spec:** 60-refactor-final
- **Severity:** minor (adjusted: nit)
- **File(s):** `docs/CHANGELOG.md`
- **Problem:** Spec 60 §5.3 / §8 / AC4 require running the suite repeatedly
  and/or with randomized order and recording a "stable green across runs" result.
  The CHANGELOG offers only a structural argument ("per-test transaction rollback
  + per-worker DBs make it order-independent") — no concrete N-run count and no
  randomized-order evidence.
- **Fix to apply:** Record a concrete, empirical flakiness result in
  `docs/CHANGELOG.md`: run the full suite multiple times and/or with randomized
  test order and document the result (e.g. "ran the suite N times / with
  randomized order: stable green"). The recorded evidence must be true — actually
  run the suite the stated number of times (and/or in randomized order) before
  writing the number. Adding the `pytest-randomly` dependency is **out of scope**
  for this pack (it would require editing `backend/pyproject.toml`, which is not
  in scope); satisfy this with documented repeated/randomized runs using existing
  tooling (e.g. invoking pytest several times, or `-p no:cacheprovider` ordering
  variation) and recording the outcome. Keep the structural rationale, but make
  the empirical run-count explicit.

### Issue 182 — Agent E2E omits streamed-text, tool-row, and Stop/cancel assertions

- **ID:** 182
- **Source spec:** 46-agent-chat-ui
- **Severity:** major (adjusted: major)
- **File(s):** `frontend/e2e/agent.spec.ts`
- **Problem:** The sole E2E test asserts only the "Review changes" button and the
  diff-apply outcome (`agent.spec.ts:13-41`). Spec 46 §8 requires the E2E to
  also assert: (a) streamed assistant text content appears; (b) a tool-activity
  row appears; and (c) clicking **Stop** on a longer scripted run shows a
  cancelled marker.
- **Fix to apply:** Extend `frontend/e2e/agent.spec.ts` so it:
  1. Asserts that **streamed assistant text** appears in the transcript.
  2. Asserts that a **tool-activity row** (`ToolActivityRow`) appears.
  3. Drives a **longer scripted run**, clicks **Stop**, and asserts the
     **cancelled marker** appears.
  Reuse the existing scripted-agent fixtures/harness already used by this spec;
  do not invent a new fixture mechanism. If a longer scripted run requires a
  fixture variant, add it within the existing fixture pattern used by
  `agent.spec.ts`. Keep selectors consistent with the component implementation
  (e.g. `transcript.tsx`, `ToolActivityRow`). Combine this with issue 198 below
  (same file).

### Issue 198 — Diff-review E2E omits reject-one-hunk → preview-updates flow

- **ID:** 198
- **Source spec:** 47-diff-review-ui
- **Severity:** minor (adjusted: minor)
- **File(s):** `frontend/e2e/agent.spec.ts`
- **Problem:** Spec 47 §8 specifies the E2E flow as: open editor → chat → Review
  changes → **reject one hunk** → **preview updates** → Apply → confirm → assert
  the accepted change is present and the rejected one is absent. The current test
  calls `review.applyAll()` with no preceding rejection, no preview-update
  assertion, and no assertion that a rejected hunk's text is absent.
- **Fix to apply:** Extend `frontend/e2e/agent.spec.ts` so the diff-review flow:
  1. Rejects **one** hunk.
  2. Asserts the **preview updates** to reflect the rejection.
  3. Applies the remaining hunks and confirms.
  4. Asserts the **accepted** change is present in `editor.content()` **and** the
     **rejected** hunk's text is **absent**.
  Implement this together with issue 182 (same file) — ideally as one coherent
  E2E that exercises streaming, a tool row, hunk rejection, preview update,
  apply, and (in a second scripted scenario) Stop/cancel. Keep total E2E runtime
  within budget; reuse scripted fixtures so no real LLM/Tectonic calls occur.

### Issue 50 — RenameProjectDialog has no unit test

- **ID:** 50
- **Source spec:** 16-project-dashboard-ui
- **Severity:** minor (adjusted: minor)
- **File(s):** `frontend/src/features/projects/project-dialogs.test.tsx`
- **Problem:** Spec 16 §8 requires a `RenameProjectDialog` unit test covering
  pre-fill with the current name, Esc-to-cancel, and confirm wording.
  `project-dialogs.test.tsx` has a full `describe('DeleteProjectDialog')` block
  (and a `CreateProjectDialog` one) but **no** `describe('RenameProjectDialog')`
  block. The component exists (`project-dialogs.tsx`, the `RenameProjectDialog`
  export).
- **Fix to apply:** Add a `describe('RenameProjectDialog')` block to
  `frontend/src/features/projects/project-dialogs.test.tsx` asserting:
  1. The text input is **pre-filled** with the current project name on open.
  2. **Esc** cancels the dialog (no rename callback fired / dialog closes).
  3. The **confirm** wording matches the component (e.g. the confirm button
     label / dialog copy).
  Follow the existing test patterns in the same file (imports, render helpers,
  RTL queries) used by the `DeleteProjectDialog` block. Import
  `RenameProjectDialog` from the component module already imported there.

### Issue 138 — Viewer-update integration test never proves "no broadcast"

- **ID:** 138
- **Source spec:** 34-access-control
- **Severity:** minor (adjusted: minor)
- **File(s):** `backend/tests/integration/test_collab_ws_access.py`
- **Problem:** AC7 requires that a dropped viewer update is "not broadcast to any
  other client". `test_viewer_update_is_dropped`
  (`test_collab_ws_access.py:78-95`) connects only one client and asserts
  `CrdtUpdate` DB count == 0 (a persistence check); it never connects a second
  client to verify no broadcast occurs.
- **Fix to apply:** Extend `test_viewer_update_is_dropped` (or add an adjacent
  test in the same file) so that: a **second** client (an **editor** on the same
  document) is connected; the **viewer** sends an update; then assert the
  **editor client receives nothing** (no relayed update) within a short timeout,
  in addition to the existing `CrdtUpdate` count == 0 assertion. Use the existing
  WebSocket test helpers/fixtures in the file; assert "no message received" with
  a bounded wait (e.g. expect a timeout / empty receive) so the test stays fast
  and deterministic.

### Issue 97 — Synctex API client placed in the wrong directory

- **ID:** 97
- **Source spec:** 26-synctex
- **Severity:** nit (adjusted: nit)
- **File(s):** `frontend/src/features/pdf-preview/synctex.ts`
- **Problem:** Spec 26 §5.3 says the API client should live at
  `frontend/src/lib/api/synctex.ts`. The implementation placed it at
  `frontend/src/features/pdf-preview/synctex.ts` (co-located with its
  consumers). Functionally identical; no behaviour breaks. `lib/api/synctex.ts`
  does not exist.
- **Fix to apply:** Prefer the **low-risk** resolution that does not pull files
  outside this pack's scope:
  - **Preferred (documentation-only):** Add a short header comment at the top of
    `frontend/src/features/pdf-preview/synctex.ts` recording that the synctex API
    client is deliberately co-located with its `pdf-preview` consumers (feature
    co-location convention) rather than under `lib/api/`, noting this is a
    knowing deviation from spec 26 §5.3. This resolves the nit without touching
    import sites in other files.
  - **Only if it does not require editing files outside this pack:** move the
    file to `frontend/src/lib/api/synctex.ts` and update its importers. Because
    moving it would require editing consumer files that are **not** in this
    pack's scope, the move is **not** permitted in this pack — use the
    documentation-only resolution above. (This keeps the pack parallel-safe.)

## 4. Acceptance criteria

1. **(236)** `backend/Dockerfile` contains a comment explaining that
   `postgresql-dev` (builder) and `libpq` (runtime) are intentionally omitted
   because `asyncpg` speaks the Postgres wire protocol natively; the packages are
   still **not** installed.
2. **(251)** `docs/CHANGELOG.md` contains explicit per-area scan records for
   areas 3 (Collaboration/CRDT), 4 (Compilation), and 5 (AI agent), with "none
   found" where clean.
3. **(250)** The spec-60 findings in `docs/CHANGELOG.md` are recorded in the
   structured format (id, area, description, severity, risk-of-fix, value-of-fix,
   decision, change-ref/rationale), matching the prior refactor-pass convention.
4. **(253)** `docs/CHANGELOG.md` records a concrete, true empirical flakiness
   result (N repeated runs and/or randomized order → stable green).
5. **(182)** `frontend/e2e/agent.spec.ts` asserts streamed assistant text
   appears, a tool-activity row appears, and a longer scripted run can be Stopped
   with a cancelled marker shown.
6. **(198)** `frontend/e2e/agent.spec.ts` rejects one hunk, asserts the preview
   updates, applies, and asserts the accepted change is present while the
   rejected hunk's text is absent.
7. **(50)** `frontend/src/features/projects/project-dialogs.test.tsx` has a
   `describe('RenameProjectDialog')` block asserting pre-fill, Esc-to-cancel, and
   confirm wording.
8. **(138)** `backend/tests/integration/test_collab_ws_access.py` connects a
   second (editor) client and asserts it receives **no** broadcast of the
   dropped viewer update, in addition to the existing persistence assertion.
9. **(97)** `frontend/src/features/pdf-preview/synctex.ts` documents the
   deliberate feature co-location deviation from spec 26 §5.3 (documentation-only
   resolution).
10. The full test suite passes (backend pytest + frontend Vitest; E2E as
    configured) and stays under the 2-minute budget; lint/format/type-check
    remain clean.

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Slow work (real LaTeX, real LLM, real network) must stay stubbed/scripted.

- **Existing green:** Before changing anything, run the backend and frontend
  suites to confirm a green baseline. After fixes, re-run; nothing previously
  green may regress.
- **New / updated tests:**
  - **(50)** New `describe('RenameProjectDialog')` Vitest+RTL cases: pre-fill,
    Esc-to-cancel, confirm wording.
  - **(138)** Updated/added integration case in `test_collab_ws_access.py`:
    second editor client receives no broadcast (bounded-wait "no message"
    assertion) plus existing `CrdtUpdate` count == 0.
  - **(182, 198)** Updated `frontend/e2e/agent.spec.ts`: streamed text, tool row,
    reject-one-hunk → preview-updates → apply (accepted present, rejected
    absent), and a Stop/cancel scenario showing the cancelled marker — all using
    scripted fixtures (no real LLM/Tectonic).
- **Docs verification (no runtime test):** Confirm `docs/CHANGELOG.md` and
  `backend/Dockerfile` edits read correctly; if `backend/tests/unit/test_docs.py`
  (out of scope here) asserts CHANGELOG structure, ensure your edits keep it
  green (do not edit that test in this pack).
- **Performance/budget note:** All new unit/integration tests are fast and
  mock/stub external services. The E2E additions reuse scripted agent fixtures so
  no real LLM or Tectonic call occurs; keep added E2E steps minimal to stay
  within the suite budget.

## 6. Definition of Done

- [ ] All issues in §3 (236, 251, 250, 253, 182, 198, 50, 138, 97) fixed
      exactly as described.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 are written and green; no previously green test
      regresses.
- [ ] Full test suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff for backend touched files; ESLint +
      Prettier + tsc for frontend touched files).
- [ ] Only files listed in §2 were edited (parallel-safe).
- [ ] No Overleaf code copied.
