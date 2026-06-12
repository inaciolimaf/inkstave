# Spec 78 — Fix-pack: infra, docs & spec-deviation cleanup (batch 2) (requirements)

## 1. Summary

This fix-pack remediates **9 confirmed issues** — all from validation review of
already-implemented specs — whose files are disjoint from every other fix-pack.
The issues span backend interface/spec alignment, two frontend file-tree-node
behaviours, documentation completeness, a CI/CD smoke-test gap, and one
spec-text path correction. Each is small and self-contained.

**Fixes:** 9 issues across 6 files.

**Severity breakdown:** 0 major · 4 minor · 5 nit.

| ID  | Source spec | Severity | Area |
|-----|-------------|----------|------|
| 20  | 07-jwt-authentication | nit | Redis family-revocation key name |
| 19  | 07-jwt-authentication | nit | `store_refresh` signature vs spec |
| 57  | 17-file-tree-ui | minor | slow double-click → inline rename |
| 61  | 17-file-tree-ui | nit | `aria-setsize`/`aria-posinset` on tree items |
| 246 | 58-documentation | nit | empty env-var Description cells |
| 244 | 58-documentation | minor | env-var table missing required?/used-by columns |
| 140 | 35-refactor-collaboration | minor | ADR 0034 stale `AuthorizationService` reference |
| 242 | 57-ci-cd-bootstrap | minor | CD smoke test missing `/ws` check |
| 106 | 28-crdt-backend-pycrdt | nit | spec path `backend/app/collab/` → `backend/src/inkstave/collab/` |

## 2. Files in scope

Edit **only** these files:

- `backend/src/inkstave/auth/refresh_store.py`
- `docs/admin-guide.md`
- `docs/adr/0034-access-control.md`
- `frontend/src/features/file-tree/file-tree-node.tsx`
- `.github/workflows/cd.yml` *(the payload lists this as `github/workflows/cd.yml`;
  the real path is `.github/workflows/cd.yml` — edit that file)*
- `specs/28-crdt-backend-pycrdt/spec.md`

**Restrict edits to the files above.** Do not modify other source, tests,
migrations, or config. Where a fix is "spec-or-code" (issues 19 and 20), this
pack resolves it by **updating the spec text to match the correct implementation**
(the impl is correct/clearer), so the in-scope file for those is the spec — but
note both issues' payload files point at `refresh_store.py`. To keep the change
minimal and behaviour-preserving, **add a short clarifying comment in
`refresh_store.py`** documenting the intentional divergence (see §3). Do not
change runtime behaviour of `refresh_store.py`.

## 3. Issues to fix

### Issue 20 — Redis family-revocation key name diverges from spec
- **Source spec:** 07-jwt-authentication · **Severity:** nit
- **File:** `backend/src/inkstave/auth/refresh_store.py`
- **Problem:** Spec 07 §5.1 defines the family-revocation key as
  `refresh_family:{family_id}`, but the implementation uses
  `_FAMILY_REVOKED_PREFIX = "refresh_family_revoked:"` (line 23). Semantics are
  identical; the implementation name is arguably clearer.
- **Fix to apply:** Keep the implementation's clearer key name (no behavioural
  change — renaming a live Redis key prefix would be riskier than the nit). Add a
  short inline comment next to `_FAMILY_REVOKED_PREFIX` recording that this is the
  intentional, clearer rename of spec 07 §5.1's `refresh_family:` marker (same
  semantics: marks an entire refresh lineage as revoked). This converts the
  undocumented divergence into a recorded decision.

### Issue 19 — `store_refresh` signature diverges from spec
- **Source spec:** 07-jwt-authentication · **Severity:** nit
- **File:** `backend/src/inkstave/auth/refresh_store.py`
- **Problem:** Spec 07 §5.3 declares
  `store_refresh(jti, user_id, family_id, expires_at)` (4 params). The
  implementation is `store_refresh(self, jti, user_id, family_id)` (line 57) and
  computes expiry internally from `self._ttl`. Behaviour is correct; the parameter
  contract differs.
- **Fix to apply:** Keep the TTL-derived implementation (it is correct and
  avoids a redundant/contradictory caller-supplied expiry). Add a short docstring
  or inline comment on `store_refresh` recording that the TTL/expiry is derived
  from settings (`self._ttl`) rather than passed as `expires_at`, intentionally
  diverging from spec 07 §5.3's signature for a single source of truth on TTL. Do
  not change the signature or behaviour.

### Issue 57 — Slow double-click on label should start inline rename
- **Source spec:** 17-file-tree-ui · **Severity:** minor
- **File:** `frontend/src/features/file-tree/file-tree-node.tsx`
- **Problem:** Spec §5.3.5 lists "slow double-click on the label → the label
  becomes an InlineRenameInput". The current `onDoubleClick` handler (line ~144)
  calls `ctx.onActivate(node)` (toggle for folders, select for docs) — it never
  starts a rename. Rename is still reachable via F2/context menu, so it is not
  blocked, but the specified path is absent.
- **Fix to apply:** Wire a double-click on the **label** of a renameable entity to
  call the existing `startRename(node)` flow (the same one F2/context-menu use)
  instead of (or in addition to) `onActivate`. Use the context's existing rename
  starter (e.g. `ctx.startRename` / whatever the panel exposes). Ensure this
  applies to renameable entities (docs and folders that can be renamed) and does
  not break the existing single-click select / folder-toggle behaviour. If the
  row-level `onDoubleClick` must keep activating, scope the rename trigger to the
  label element specifically per §5.3.5.

### Issue 61 — `aria-setsize` / `aria-posinset` absent on tree items
- **Source spec:** 17-file-tree-ui · **Severity:** nit
- **File:** `frontend/src/features/file-tree/file-tree-node.tsx`
- **Problem:** Spec §5.3.8 lists `aria-setsize`/`aria-posinset` "where practical".
  The `<li role="treeitem">` sets `aria-level`, `aria-selected`, `aria-expanded`
  but neither `aria-setsize` nor `aria-posinset`, reducing "item N of M"
  announcements.
- **Fix to apply:** Thread the node's index among its siblings and the sibling
  count into `FileTreeNode` (props such as `index` and `siblingCount`, supplied by
  the parent that maps over the sibling list), and emit
  `aria-posinset={index + 1}` and `aria-setsize={siblingCount}` on the
  `role="treeitem"` `<li>`. If the parent that renders the sibling list is in a
  **different** file, derive the values another in-file way is not possible — in
  that case pass them from the list render site **only if that site is within an
  in-scope file**; otherwise add the props with values computed from data already
  available to `FileTreeNode`. Do not modify out-of-scope files; if the sibling
  count is not available without touching an out-of-scope file, document that the
  attribute is emitted using the data available in this component and leave a TODO
  noting the "where practical" hedge. (Prefer the clean prop-threading solution if
  the render site is in-scope.)

### Issue 246 — Empty env-var Description cells
- **Source spec:** 58-documentation · **Severity:** nit
- **File:** `docs/admin-guide.md`
- **Problem:** Several env-var rows have empty Description cells: `DATABASE_URL`,
  `REDIS_URL`, `TEST_DATABASE_URL` (lines ~62–64), `JWT_SECRET`,
  `JWT_SECRET_PREVIOUS`, `OPENROUTER_API_KEY`, and several `AGENT_*` rate/cost rows
  (lines ~103–104, 175, 199–206).
- **Fix to apply:** Fill in a concise, accurate Description for each empty cell,
  matching the meaning documented in `.env.example` / the corresponding spec. For
  example: `DATABASE_URL` — primary async PostgreSQL DSN used by the backend and
  Alembic; `REDIS_URL` — Redis connection used for refresh tokens, presence, and
  ARQ jobs; `TEST_DATABASE_URL` — PostgreSQL DSN used only by the integration test
  suite; `JWT_SECRET` — HMAC signing secret for access/refresh tokens;
  `JWT_SECRET_PREVIOUS` — prior signing secret accepted during key rotation;
  `OPENROUTER_API_KEY` — API key for the OpenRouter-backed LLM client; `AGENT_*` —
  describe each rate/cost limit. Keep descriptions one line each and consistent
  with neighbouring rows.

### Issue 244 — Env-var table missing `Required?` and `Used by` columns
- **Source spec:** 58-documentation · **Severity:** minor
- **File:** `docs/admin-guide.md`
- **Problem:** Spec 58 §5.3 requires the env-var table to have **5 columns**: name,
  required?, default, description, which services use it. The current header (line
  ~55) is `| Variable | Default | Description |` (3 columns); `Required?` and
  `Used by (services)` are absent.
- **Fix to apply:** Restructure the env-var reference table to the 5 required
  columns: `| Variable | Required? | Default | Description | Used by (services) |`.
  Populate every existing row: `Required?` = Yes/No (Yes for secrets/DSNs with no
  safe default, No for ones with defaults), and `Used by (services)` listing the
  service(s) that consume each var (e.g. backend, collab/websocket, worker/ARQ,
  frontend build, nginx). Keep the values consistent with `.env.example` and the
  service prefixes already described in the prose above the table. Combine cleanly
  with issue 246's Description fixes (do both in one coherent table).

### Issue 140 — ADR 0034 stale `AuthorizationService` reference
- **Source spec:** 35-refactor-collaboration · **Severity:** minor
- **File:** `docs/adr/0034-access-control.md`
- **Problem:** ADR 0034 (line ~20) still states "`AuthorizationService` resolves a
  user's role from memberships", but that class was removed by spec 35 (documented
  in `docs/refactors/35-collaboration.md` F-2) and replaced by `role_for` + the
  dependency's `_resolve` helper. The ADR was never updated.
- **Fix to apply:** Update the ADR's Decisions section so it no longer presents
  `AuthorizationService` as current. Note that `AuthorizationService` was removed
  in spec 35 (refactor) and role resolution is now performed by `role_for` plus the
  access-control dependency's `_resolve` helper. Add a short "Superseded/Updated by
  spec 35" note (or amend the relevant sentence) so the ADR reflects current
  reality while preserving the original decision's historical intent.

### Issue 242 — CD smoke test missing `/ws` WebSocket-upgrade check
- **Source spec:** 57-ci-cd-bootstrap · **Severity:** minor
- **File:** `.github/workflows/cd.yml`
- **Problem:** Spec 57 §5.2.2 requires the CD workflow to run spec 56 §8's image
  smoke job, which includes verifying a WebSocket upgrade at `/ws`. The CD smoke
  step (cd.yml lines ~46–68 / ~61–67) checks only `/` (SPA), `/api/setup/status`,
  and `/metrics` blocked — no WebSocket-upgrade probe to `/ws`, leaving the nginx
  WebSocket proxy path unverified.
- **Fix to apply:** Add a `/ws` WebSocket-upgrade probe to the CD smoke step.
  Use a `curl` request with the upgrade headers (`-H 'Connection: Upgrade'`,
  `-H 'Upgrade: websocket'`, plus the `Sec-WebSocket-Key`/`Sec-WebSocket-Version`
  headers) against the running container's `/ws` endpoint and assert an **HTTP 101
  Switching Protocols** response (or otherwise confirm the proxy upgrades rather
  than 404/502). Match the style of the existing smoke checks (same shell step,
  fail the job on a non-101 response). Mirror the exact probe used by spec 56 §8 if
  one already exists in the repo.

### Issue 106 — Spec 28 uses wrong module path
- **Source spec:** 28-crdt-backend-pycrdt · **Severity:** nit
- **File:** `specs/28-crdt-backend-pycrdt/spec.md`
- **Problem:** Spec 28 repeatedly writes the module path as `backend/app/collab/`
  (lines 33, 109, 111, 137, 165, 188, 204, 246), but the actual code lives at
  `backend/src/inkstave/collab/`. This is a documentation-only inconsistency in the
  spec text; the implementation correctly uses the project's `src` layout.
- **Fix to apply:** Replace every `backend/app/collab/` occurrence in
  `specs/28-crdt-backend-pycrdt/spec.md` with `backend/src/inkstave/collab/`. Do a
  full pass so no `backend/app/collab/` references remain.

## 4. Acceptance criteria

1. `refresh_store.py` carries a comment recording the intentional
   `refresh_family_revoked:` key-name divergence from spec 07 §5.1 (issue 20); no
   behavioural change.
2. `refresh_store.py` `store_refresh` carries a comment/docstring recording that
   expiry is TTL-derived (intentional divergence from spec 07 §5.3's `expires_at`
   parameter) (issue 19); signature/behaviour unchanged.
3. Double-clicking a renameable entity's **label** in `file-tree-node.tsx` starts
   the inline rename flow (issue 57), without breaking single-click select / folder
   toggle.
4. Tree items in `file-tree-node.tsx` emit `aria-posinset` and `aria-setsize`
   (issue 61).
5. Every env-var row in `docs/admin-guide.md` has a non-empty Description (issue
   246).
6. The `docs/admin-guide.md` env-var table has 5 columns —
   `Variable | Required? | Default | Description | Used by (services)` — with every
   row populated (issue 244).
7. `docs/adr/0034-access-control.md` no longer presents `AuthorizationService` as
   current; it notes the spec-35 removal and the `role_for` + `_resolve`
   replacement (issue 140).
8. `.github/workflows/cd.yml` smoke step probes `/ws` for a WebSocket upgrade and
   fails the job if the upgrade does not succeed (issue 242).
9. `specs/28-crdt-backend-pycrdt/spec.md` contains no `backend/app/collab/`
   references; all replaced with `backend/src/inkstave/collab/` (issue 106).
10. The full test suite (including any docs-validation test that checks
    `admin-guide.md`) stays green and under 2 minutes; only §2 files are modified.

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Existing green:** Run the docs-validation test for `admin-guide.md` (the test
  that checks every `.env.example` variable appears) and the file-tree frontend
  unit tests before changes to confirm baseline green.
- **New/updated tests:**
  - *file-tree-node:* add/extend a Vitest assertion that a label double-click
    triggers the rename input (issue 57) and that a tree item renders
    `aria-posinset`/`aria-setsize` (issue 61) — keep these in the existing
    file-tree test file if it is already in the test tree (it is **not** in this
    pack's edit set, so only add assertions there if that file is already a test
    file you may extend; if extending an out-of-scope test file is required,
    instead rely on the component-level change and confirm via the existing tests).
    Prefer not to add new test files outside §2; the component change must keep
    existing tests green.
  - *docs:* the existing docs-validation test must still pass after the table
    restructure; verify variable names are preserved.
  - *cd.yml:* YAML must remain valid; the new smoke step uses standard `curl`.
- **Run:**
  - `npm --prefix frontend run test -- file-tree`
  - `pytest backend/tests -k admin_guide or docs` (adjust to the real docs test name)
- **Performance/budget note:** All changes are docs/spec text, a CI YAML step, and
  small component edits; negligible test-runtime impact.

## 6. Definition of Done

- [ ] All 9 issues (20, 19, 57, 61, 246, 244, 140, 242, 106) fixed exactly as in
      §3.
- [ ] All acceptance criteria in §4 pass.
- [ ] Only the six files in §2 are modified.
- [ ] No backend runtime behaviour changed (issues 19/20 are documentation
      comments only).
- [ ] Affected frontend (Vitest) and docs-validation tests are green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean; `cd.yml` is valid YAML.
- [ ] No Overleaf code copied.
