# Spec 63 — Runtime Seed & Setup (requirements)

## 1. Summary

This spec makes a fresh Inkstave instance immediately usable and explorable. The
backend already has an idempotent `seed_demo` and the `/api/setup/status` +
`/api/setup/admin` endpoints; this spec (a) confirms/strengthens the seed so a
freshly-seeded app opens to a working **multi-file** LaTeX project, (b) adds the
**missing frontend `/setup` route** that calls `GET /api/setup/status` and routes
a brand-new deployment to admin creation, and (c) locks both down with fast tests
(idempotent seed via the test DB; `/setup` rendering via a route test).

## 2. Context & dependencies

- **Depends on:** spec 09 (frontend `createBrowserRouter` routing, `apiClient`,
  auth context), spec 57 (`backend/src/inkstave/bootstrap/seed.py::seed_demo`,
  `backend/src/inkstave/bootstrap/admin.py`, `backend/src/inkstave/api/routes/setup.py`,
  and the `seed` CLI subcommand).
- **Unlocks:** a real out-of-the-box first run; complements spec 62 (config) so a
  fresh deploy both validates config and bootstraps an explorable state.
- **Affected areas:** backend (verify/extend `seed.py`), frontend (new `/setup`
  route + page + a tiny setup API call), tests (pytest + Vitest route test).

## 3. Goals

- Running the seed twice leaves the DB in the **same** state (idempotent): a demo
  user, a demo project, and a **multi-file** LaTeX tree (at least `main.tex` plus
  one more file, e.g. a `sections/` folder with an included `.tex`, or a
  `references.bib`) with non-empty document content.
- A new frontend route `/setup` renders a minimal page that calls
  `GET /api/setup/status`; when `needs_setup === true` it shows an admin-creation
  form (posting to `POST /api/setup/admin`); a fresh deployment is routed there.
- DB-state assertions prove the seeded rows exist and that a second run does not
  duplicate them.

## 4. Non-goals (explicitly out of scope)

- No change to the `/api/setup` backend endpoints or their schemas (already
  built in spec 57); this spec consumes them from the frontend.
- No admin dashboard / user-management UI beyond the minimal first-run admin
  creation form.
- No automatic seeding in production; the demo seed remains dev/test only
  (existing prod guard with `force=True` override stays).
- No real LaTeX compile of the seeded project in tests.

## 5. Detailed requirements

### 5.1 Data model (if any)

None — uses existing `User`, `Project`, `TreeEntity` (folders/docs), `Document`
content models. No new migration.

### 5.2 Backend / API (if any)

Current state (verify, then extend minimally):

- `seed_demo(session, hasher, *, settings, force=False) -> bool` in
  `/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/bootstrap/seed.py`
  today creates: demo user (`demo@example.com` / `demoPassw0rd`), `Demo Project`,
  the auto root folder, a single `main.tex` doc, and starter LaTeX content. It is
  already idempotent (returns `False` if `demo@example.com` already exists) and
  refuses to run in prod unless `force=True`.
- It reuses: `create_project` (`backend/src/inkstave/services/project.py`),
  `create_entity` (`backend/src/inkstave/services/tree_service.py`),
  `ensure_document` / `set_content_from_collab`
  (`backend/src/inkstave/services/document_service.py`), and the argon2 hasher
  from `backend/src/inkstave/auth/password.py`.
- The setup endpoints in
  `/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/api/routes/setup.py`:
  `GET /api/setup/status` → `{ "needs_setup": <bool> }`;
  `POST /api/setup/admin` (body `RegisterRequest{email,password,display_name}`)
  → `201 UserPublic`, and `409` once an admin exists.

Requirements:

1. **Multi-file seed.** Extend `seed_demo` so the demo project is genuinely
   multi-file: in addition to `main.tex`, create at least one more tree entity —
   e.g. a `sections/` folder containing `intro.tex` (with `\section{...}` body),
   and have `main.tex` `\input{sections/intro}` — and/or a `references.bib`. All
   created docs must have **non-empty** content via the existing content helper.
   Keep the whole thing inside one transaction and preserve idempotency (the
   `demo@example.com` existence check still short-circuits a second run).
2. **Idempotency preserved.** A second `seed_demo` call (without `force`) returns
   `False` and adds **no** new rows. With `force=True` in a non-prod env it must
   not create duplicate users/projects for the same demo email (no-op or safe
   re-use — pick the simplest that keeps the row counts stable).
3. No change to the `seed` CLI subcommand contract beyond what the multi-file
   change requires.

### 5.3 Frontend / UI (if any)

Current state: `/home/inacio/Área de trabalho/code/inkstave/frontend/src/App.tsx`
uses `createBrowserRouter` with routes `/login`, `/register`,
`/settings/confirm-email`, and an auth-guarded group (`/`, `/projects`,
`/projects/:projectId`, `/settings`, `/invite/:token`) plus a catch-all. There is
**no `/setup` route**, and no frontend call to `/api/setup/status` exists today.

Requirements:

1. **New `/setup` route + page.** Add a public route `/setup` (sibling of
   `/login`, not behind `RequireAuth`) rendering a new `SetupPage` component
   (suggested path
   `/home/inacio/Área de trabalho/code/inkstave/frontend/src/pages/setup-page.tsx`).
   The page:
   - Calls `GET /api/setup/status` (add a small typed helper, e.g.
     `getSetupStatus(): Promise<{ needsSetup: boolean }>`, wherever the other
     frontend API helpers live; convert the wire `needs_setup` → `needsSetup`).
   - While loading: a loading state. On error: a friendly error state (reuse
     existing `Alert`/`Skeleton` from `frontend/src/components/ui/`).
   - When `needsSetup === true`: render a minimal admin-creation form
     (email + password + display name, using existing shadcn form components)
     that posts to `POST /api/setup/admin`; on success route to `/login`.
   - When `needsSetup === false`: redirect to `/login` (setup already done).
2. **Route a fresh deployment to `/setup`.** Add a minimal gate so a brand-new
   deployment lands on `/setup`. Simplest acceptable approach: in the app
   bootstrap (auth context / a small top-level effect), when the user is
   **unauthenticated**, check `GET /api/setup/status`; if `needsSetup` is true,
   navigate to `/setup` instead of `/login`. Keep this cheap and non-blocking for
   the already-set-up case (a single status call). Do **not** call it for
   authenticated users.

Keep the page minimal — prefer existing shadcn/ui components; no bespoke CSS.

### 5.4 Real-time / jobs / external integrations (if any)

None.

### 5.5 Configuration

No new env vars. Seed credentials remain the existing constants in `seed.py`
(`demo@example.com` / `demoPassw0rd`). Note in docs that these are dev-only.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently.

- `services/web/app/src/Features/ServerAdmin/` and Overleaf's first-launch /
  admin-bootstrap flow — learn the "if no admin, force setup" routing idea only.
- Overleaf's example/template project bootstrap (the default project content a new
  user gets) — learn the "seed a working sample" idea; do not copy any `.tex`.
- A consolidated idempotent `seed_demo` + a dedicated `/setup` SPA route is
  Inkstave's own composition; build it from this spec.

## 7. Acceptance criteria

1. **Given** an empty test DB, **when** `seed_demo` runs once, **then** it returns
   `True` and the DB contains the demo user, a demo project, and a multi-file tree
   (`main.tex` plus at least one more doc), each doc with non-empty content.
2. **Given** a DB already seeded, **when** `seed_demo` runs a second time without
   `force`, **then** it returns `False` and the row counts (users, projects, tree
   entities, documents) are **unchanged**.
3. **Given** the seeded project, **when** its tree is listed, **then** at least
   two document entities exist and `main.tex` references the additional file
   (e.g. via `\input{...}`), demonstrating a working multi-file project.
4. **Given** a fresh deployment where `GET /api/setup/status` returns
   `needs_setup: true`, **when** an unauthenticated visitor loads the app, **then**
   they are routed to `/setup`.
5. **Given** the `/setup` route with `needsSetup === true`, **when** `SetupPage`
   renders, **then** it shows the admin-creation form (email/password/display
   name fields and a submit control).
6. **Given** the `/setup` route with `needsSetup === false`, **when** `SetupPage`
   renders, **then** it redirects to `/login` (no admin form shown).
7. **Given** a valid admin-creation submission, **when** the form posts to
   `POST /api/setup/admin` and succeeds, **then** the user is routed to `/login`.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Unit / Integration (pytest):**
  - In `backend/tests/integration/test_seed_63.py` (new), or extend
    `backend/tests/integration/test_bootstrap_57.py`: using the `db_session` and
    the test argon2 hasher, call `seed_demo` and assert AC1 (rows + multi-file +
    non-empty content), then call it again and assert AC2 (returns `False`, row
    counts stable — capture counts with `select(func.count())` before/after).
    Assert AC3 by listing the project's tree entities and checking `main.tex`
    content `\input`s the second file. Mirror existing fixtures
    (`test_seed_demo_is_idempotent_in_dev` already covers the basic idempotency
    shape — extend, don't duplicate).
- **Frontend route / component test (Vitest + RTL):**
  - In `frontend/src/pages/setup-page.test.tsx` (new): mock the setup API helper
    (or global `fetch`) following the patterns in
    `frontend/src/features/projects/projects-page.test.tsx` and
    `frontend/src/auth/require-auth.test.tsx`. Use `renderWithProviders` from
    `frontend/src/test/utils.tsx` with `route: "/setup"`. Assert AC5 (form shown
    when `needsSetup` true) and AC6 (redirect to `/login` when false). Optionally
    assert AC7 by mocking a successful `POST` and checking navigation.
  - Add/extend a routing test (e.g. `frontend/src/App.test.tsx` or alongside
    `require-auth.test.tsx`) for AC4: with the status mock returning
    `needs_setup: true` and an unauthenticated context, assert the app lands on
    `/setup`. Keep it a focused unit test with `MemoryRouter`/`renderWithProviders`,
    not a full e2e.
- **E2E (Playwright):** none (fast tier only).
- **Performance/budget note:** Seed tests use the existing transactional test DB
  (rolled back per test); frontend tests mock fetch — no real services, no real
  compile. Negligible time added.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (multi-file idempotent seed; `/setup`
      route + page + fresh-deploy routing).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes (measure with `just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, `mypy`, ESLint/Prettier, `tsc`).
- [ ] No new env vars; dev-only demo credentials noted in docs.
- [ ] No Overleaf code copied (including no copied sample `.tex` content).
