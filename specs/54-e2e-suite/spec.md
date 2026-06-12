# Spec 54 — End-to-End Suite (requirements)

## 1. Summary

This spec delivers a **Playwright** end-to-end suite covering Inkstave's core
user journeys against a real (test-profile) stack: register/login → create
project → add files → edit a document → compile → preview the PDF → share &
**two-user live collaboration** → version history → the **AI agent proposes a diff
and the user applies it**. It defines the **test-environment bring-up** (a
compose/test profile), the **stubs** that keep it fast (a deterministic LLM stub,
and a mocked/precompiled or tiny Tectonic path), and which flows are **smoke**
(always run, inside the 2-minute budget) versus **full** (opt-in/nightly). It is
the integration-confidence capstone of the hardening phase.

## 2. Context & dependencies

- **Depends on:** spec **09** (frontend foundation, routing, API client, auth
  pages), **16** (project dashboard UI), **17** (file-tree UI), **18** (CodeMirror
  editor), **19** (autosave/REST sync), **24** (PDF.js preview + compile button +
  log panel), **31** (Yjs binding / live sync), **32** (presence/awareness UI),
  **33** (collaborators & sharing), **46** (agent chat UI), **47** (diff-review &
  apply UI). Also relies on spec **04** (Playwright setup) and spec **53** (the
  budget gate, e2e sub-budget, storage-state reuse, stubbing patterns).
- **Unlocks:** spec **55** (refactor pass leans on e2e as a regression net),
  spec **56/57** (the same compose/test profile and bring-up feed prod packaging
  and CI).
- **Affected areas:** e2e (`e2e/` or `frontend/e2e/` Playwright project), infra
  (a `docker-compose.test.yml` or test profile, an LLM stub server, a Tectonic
  stub/mode), docs (e2e strategy note).

## 3. Goals

- A Playwright project with a **smoke** suite covering the journeys in §5.3,
  tagged so the default CI run executes only smoke and stays in budget.
- A **deterministic LLM stub** so agent flows are reproducible and instant (no
  OpenRouter call).
- A **fast Tectonic path**: either a mocked compile that returns a tiny canned PDF
  + log, or a real Tectonic run against a one-page document with a warmed cache —
  chosen to keep the smoke compile under a small time bound. Default: **mocked**
  in smoke, **real** only in the full/nightly tier.
- A **bring-up** mechanism (compose/test profile or Playwright `webServer`) that
  starts backend + frontend + Postgres + Redis (+ the LLM stub) reproducibly, with
  migrations applied and a clean DB per run.
- **Auth storage-state reuse** (login once, reuse the token) so most specs skip
  the login UI (per spec 53).
- A documented **smoke vs full** split and the **time ceiling** for e2e within the
  total budget.

## 4. Non-goals (explicitly out of scope)

- Exhaustive UI coverage of every control/edge case (units/integration own those).
- Visual-regression / screenshot-diff testing.
- Real LLM and heavy real LaTeX in the **default** tier (only in opt-in full/
  nightly).
- Cross-browser matrix beyond one engine (Chromium) in the default tier; WebKit/
  Firefox runs are full/nightly at most.
- Mobile/responsive e2e.
- Performance/load via Playwright (spec 53 covers perf; this is functional).

## 5. Detailed requirements

### 5.1 Test environment bring-up

Provide a reproducible stack for e2e:

- **Option A (preferred for local + CI):** Playwright `webServer` config that
  starts the backend (Uvicorn, test profile) and the frontend (Vite preview of a
  prebuilt bundle) and waits for `/healthz`/`/readyz`; Postgres and Redis come
  from `docker-compose.test.yml` (or the CI service containers). Migrations run on
  bring-up; the DB is reset to a clean state at the start of the run.
- **Option B:** a full `docker-compose.test.yml` bringing up all services
  (including a built frontend behind the dev server/nginx) that Playwright targets
  via `BASE_URL`.

Document the chosen approach. Requirements either way:

- The **LLM stub** runs as a tiny local HTTP server (or the backend's DI swaps in
  a stub client driven by an env flag `LLM_STUB=true`) returning a deterministic,
  streamed response and a deterministic proposed diff for a known prompt.
- The **Tectonic path** is controlled by `COMPILE_MODE` (`mock` | `real`): in
  `mock`, the compile job's runner returns a fixed small PDF + log instantly; in
  `real`, it runs Tectonic with the warmed package cache (full tier only).
- A clean, seeded baseline (or empty DB + register-in-test) — prefer registering
  users within the test for the auth journey, and an API-level helper to fast-seed
  state (a project with files) for journeys that aren't about that setup, to keep
  specs short and fast.
- `BASE_URL`, ports, and credentials come from env; nothing hard-coded to a
  developer machine.

### 5.2 Suite structure & conventions

- Location: `e2e/` (or `frontend/e2e/`) with a `playwright.config.ts` defining a
  `smoke` project (default) and a `full` project (opt-in via tag/grep), one
  Chromium browser by default, `workers` from CI cores, retries `1` in CI/`0`
  locally, trace/video **on-failure only**.
- **Page objects / helpers** for the recurring surfaces (login page, dashboard,
  editor, file tree, PDF preview, share dialog, agent panel, diff review) so specs
  read as user stories and stay maintainable.
- **Auth fixture:** a global setup logs a user in once and saves `storageState`;
  specs that aren't testing login start authenticated. The login/register journey
  uses the UI directly.
- **Two-user collaboration** uses two browser contexts (User A + User B) in one
  test, each with its own storage-state, both opening the same shared project.
- Tagging: tests tagged `@smoke` run by default; `@full` only in the full project.
- **No fixed `waitForTimeout`** for app readiness — wait on selectors / network /
  text. Determinism is required (the LLM and compile are stubbed precisely for
  this).
- Each spec is independent and self-cleaning (unique emails/project names via a
  run id) so parallel workers don't collide; or the run uses an isolated DB.

### 5.3 The journeys (smoke unless noted)

Each is a Playwright spec asserting user-visible outcomes:

1. **Auth journey** (`auth.spec.ts`): register a new user via the UI → land
   logged-in (or confirm + login) → log out → log back in. Asserts redirects and
   that protected routes require auth.
2. **Project lifecycle** (`project.spec.ts`): from the dashboard, create a
   project → it appears in the list → rename it → it persists across reload →
   delete it (with confirm) → it disappears.
3. **Files & editing** (`editor.spec.ts`): open a project → create a `.tex` file
   in the tree → open it in the editor → type LaTeX → autosave persists (reload
   shows the content). Asserts the file tree reflects the new file.
4. **Compile & preview** (`compile.spec.ts`): click Compile → a job runs (stubbed)
   → the PDF preview renders (PDF.js shows ≥1 page / a canvas) → the log panel
   shows output → a deliberate LaTeX error surfaces in the log/annotations. (In
   `mock` mode the PDF is the canned one; assert the preview renders it.)
5. **Share & live collaboration** (`collab.spec.ts`, two contexts): User A shares
   the project with User B as **editor** (invite by email/handle) → User B opens
   it → both see each other's presence (cursor/online list) → User A types and
   User B sees the change **live** (and vice-versa) → a **viewer** cannot edit
   (assert read-only). This is the headline real-time test.
6. **Version history** (`history.spec.ts`): make edits producing snapshots → open
   the history timeline → see versions → view a diff → restore an earlier version
   → the editor content reflects the restore.
7. **AI agent diff** (`agent.spec.ts`): open the agent chat → send a prompt that
   the **LLM stub** answers deterministically with tool calls and a proposed
   per-file diff → the diff-review UI shows hunks → the user **applies** the diff
   (a hunk or all) → the document content updates accordingly → assert nothing was
   applied before the user clicked apply (the agent never auto-writes).

**Smoke vs full mapping:** journeys 1–7 each have a **smoke** core path (the
happy path above, stubbed). **Full** (`@full`, nightly) adds: real Tectonic
compile of a 1-page doc (journey 4), multi-hunk partial accept/reject (journey 7),
viewer/permission edge cases, and an additional browser engine. Document this
table in `docs/`.

### 5.4 Stubs & determinism

- **LLM stub contract:** given the canned prompt used by `agent.spec.ts`, the stub
  streams a fixed assistant message and emits a fixed tool-call sequence
  (search → read file → propose edit) and a fixed unified diff against the known
  seeded file. The diff applies cleanly. The stub is also used by spec 49/44's
  fast tests; reuse it. Token usage in the stub is fixed so metrics assertions are
  stable.
- **Compile stub:** `COMPILE_MODE=mock` returns a fixed valid PDF (a tiny
  pre-generated one committed to the repo) and a fixed log; the error case returns
  a log with a known error line so journey 4 can assert annotations.
- These stubs live in the test/infra layer and are selected by env; production
  code is untouched (DI/flag only).

### 5.5 Configuration

Add to `.env.example` (e2e/test scope) and document:

| Var | Default | Purpose |
| --- | --- | --- |
| `E2E_BASE_URL` | `http://localhost:5173` | where Playwright points |
| `LLM_STUB` | `true` (e2e/test) | swap the LLM client for the deterministic stub |
| `LLM_STUB_URL` | `http://localhost:8099` | if the stub is a separate server |
| `COMPILE_MODE` | `mock` (smoke) / `real` (full) | Tectonic stub vs real |
| `E2E_PLAYWRIGHT_WORKERS` | from cores | parallelism |
| `E2E_RETRIES` | `1` (CI) / `0` (local) | flake retries |

`playwright.config.ts`: `smoke` (default) and `full` projects, Chromium, trace/
video on-failure, the `webServer`/compose bring-up, `storageState` from global
setup.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` for **organization ideas only**. They are
> Mocha-acceptance / Cypress, not Playwright; transfer structure, not code.

- `services/web/test/acceptance/` — how they group acceptance tests and bring up
  the app/DB for them. Learn the shape of a self-contained acceptance suite.
- `services/web/test/frontend/` — frontend test organization (helpers, fixtures).
- `server-ce/test/` — the CE end-to-end specs (e.g. `create-and-compile-project.
  spec.ts`, `project-sharing.spec.ts`, `editor.spec.ts`, `history.spec.ts`) and
  `server-ce/cypress.config.ts` / `server-ce/cypress/` — these map almost
  one-to-one to Inkstave's journeys (create+compile, sharing/collab, editor,
  history). Learn **which journeys are worth covering and how they're scoped**,
  then write independent Playwright specs.
- `services/web/cypress.config.ts` and `services/web/cypress/` — config/structure
  ideas for browser e2e (workers, base URL, fixtures). Approach only.

## 7. Acceptance criteria

1. **Given** the smoke project, **when** `playwright test` runs in CI, **then** all
   smoke specs (journeys 1–7) pass and the e2e wall-clock fits within its
   sub-budget so the **total** suite stays under 2 minutes (per spec 53's gate).
2. **Given** the auth spec, **then** a user can register and log in via the UI,
   protected routes redirect when unauthenticated, and logout returns to the
   public state.
3. **Given** the project spec, **then** create/rename/delete reflect in the
   dashboard and persist across reload.
4. **Given** the editor spec, **then** a new `.tex` file can be created, edited,
   and its content survives a reload (autosave).
5. **Given** the compile spec in `mock` mode, **then** Compile produces a rendered
   PDF in the preview and log output, and an injected LaTeX error appears in the
   log/annotations.
6. **Given** the collab spec with two contexts, **then** sharing as editor lets
   User B open the project, both see presence, edits propagate live both ways, and
   a viewer cannot edit (read-only enforced).
7. **Given** the history spec, **then** versions appear, a diff is viewable, and a
   restore changes the editor content to the restored version.
8. **Given** the agent spec with `LLM_STUB=true`, **then** the chat streams the
   deterministic response, a proposed diff appears in the review UI, **nothing is
   applied until the user clicks apply**, and after applying, the document reflects
   the change.
9. **Given** the bring-up, **then** the stack starts reproducibly with migrations
   applied and a clean DB, on a fresh checkout, via the documented command.
10. **Given** the suite, **then** it is deterministic (no real LLM/network, stubbed
    compile, no fixed sleeps for readiness) and reruns green; flake retries are
    bounded and traces/videos are captured only on failure.
11. **Given** the `full`/`@full` project, **then** it is **excluded** from the
    default run and can be invoked explicitly (e.g. real-Tectonic compile, partial
    hunk accept), without affecting the default budget.

## 8. Test plan

> The e2e suite *is* the deliverable. It must fit inside the global 2-minute
> budget as the smoke tier (spec 53 enforces this). No real LLM/network; compile
> is mocked in smoke.

- **Smoke (Playwright, default):** the seven journey specs in §5.3, each the happy
  path, stubbed LLM and `COMPILE_MODE=mock`. Two-context collab in one spec. Auth
  via UI in `auth.spec.ts`; other specs reuse storage-state.
- **Full (`@full`, opt-in/nightly, excluded from default budget):** real Tectonic
  one-page compile, multi-hunk partial accept/reject, viewer/permission edge
  cases, an extra browser engine.
- **Harness tests:** a sanity check that the LLM stub returns the canned
  diff/stream and the compile mock returns the canned PDF/log (cheap, fast).
- **Integration with spec 53:** verify e2e uses shared bring-up + storage-state so
  it stays within its time ceiling; the budget gate measures e2e wall-clock as
  part of the total.
- **Performance/budget note:** one Chromium engine in smoke, parallel workers,
  prebuilt frontend bundle, mocked compile, deterministic stub LLM, traces only on
  failure. Heavy/real paths are quarantined to `@full`/nightly.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (suite, bring-up, stubs).
- [ ] All acceptance criteria in §7 pass.
- [ ] All journeys in §5.3 covered as smoke specs and green.
- [ ] Full suite (with e2e smoke) runs in < 2 minutes; the spec-53 gate stays
      green.
- [ ] Lint/format/type-check clean (ESLint/Prettier on the e2e project).
- [ ] New env vars documented in `.env.example`; e2e-strategy note (smoke vs full,
      bring-up, stubs) under `docs/`.
- [ ] Deterministic: no real LLM/network in default tier; compile mocked in smoke;
      no fixed readiness sleeps.
- [ ] No Overleaf code copied.
