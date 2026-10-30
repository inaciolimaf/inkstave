# CLAUDE.md — Guide for agents implementing Inkstave

This file orients any AI/automation agent (Claude Code or otherwise) working in
this repository. Read it fully before touching code.

## What this project is

Inkstave is a from-scratch, real-time collaborative LaTeX editor with a built-in
AI writing agent. It is **inspired by** Overleaf Community Edition but shares
**no code** with it. See `README.md` for the product overview and stack.

This project follows the **`project-standard`** and **`frontend-standard`** skills
(`~/.claude/skills/`; the visual identity is spec 106), except where "Deviations from the standard"
below says otherwise. A change to the standard (lint, tests, docker, CI, documentation)
applies in both places: here and in the skill.

## Documentation — read first, update together

- **`docs/system/`** explains the system as it is: one file per domain, index in
  `docs/system/README.md`. Before touching a domain, read its file.
- **Every change to the system updates the documentation in the same commit**: route,
  table, flow, rule, environment variable, new, removed or renamed file → the domain's
  file. New domain → new file + a line in the index.
- **Keep the `.md` files tidy**: when passing through a documentation file (including
  this `CLAUDE.md`, the `README.md` and the specs), fix what is outdated, duplicated or
  confusing, even if it is not part of the task.
- **This `CLAUDE.md` updates too**: new command, new convention, discovered pitfall,
  structure change → it goes here in the same commit.
- `specs/` is what was asked and why, and `docs/adr/` records past decisions. Both are
  history: they are not rewritten, and divergence from the code is recorded in
  `docs/system/`.
- `docs/known-gaps.md` lists what is knowingly unfinished. Resolving a gap removes its
  entry in the same commit.
- A new environment variable also goes in `.env.example` and the table in
  `docs/admin-guide.md`; a test fails otherwise.
- Guarantee: `make docs` (in CI).

## Language

- **The code is all in English**: identifiers, file and folder names, database tables
  and columns, API routes and fields, error types, comments, docstrings, documentation
  (`docs/`, specs, this file, README) and commit messages.
- **Only what a person reads in the product changes language.** The product is bilingual,
  English and Portuguese: interface text lives in the react-i18next locale files, one
  namespace per feature. Backend error messages and e-mails are English-only for now
  (`docs/known-gaps.md`).
- **The English interface strings must stay byte-identical**: tests assert on them.
- **Every domain name comes from `docs/glossary.md`** (domain term → name in code →
  Portuguese product term). A new term enters the glossary in the same commit that
  introduces it.
- **Never renamed**: environment variables configured on a server (the settings field may
  have another name and read the variable by alias; a new variable comes with a safe
  default or with a notice to the server owner listing what to configure), CLI commands
  and Makefile targets (only by agreement), past commits.

## The golden rules

1. **Implement specs strictly in order.** The source of truth is `specs/`.
   Implement `01` fully (code + passing tests) before starting `02`, and so on.
   Never skip ahead; later specs assume earlier ones exist.
2. **Never copy Overleaf code.** Overleaf is AGPLv3; Inkstave is MIT. You may
   *read* the Overleaf repo (cloned at `../overleaf/`) to understand an approach,
   but every line you write must be your own independent implementation. Do not
   copy, paste, or mechanically translate Overleaf source. If a spec points you
   at an Overleaf file, treat it as a textbook, not a clipboard.
3. **Keep the full test suite under 2 minutes.** Unit + integration + e2e
   combined. If something is slow (LaTeX compile, real LLM call), it belongs in
   an async ARQ job and must be stubbed/mocked in tests. Measure before merging.
4. **A spec is done only when its Definition of Done and Acceptance criteria
   pass, including the tests it requires.** "It runs" is not "it's done".
5. **Match the existing style.** Once early specs establish conventions
   (project layout, naming, error handling, test patterns), follow them. Read
   neighbouring code before adding new code.

## Tech stack (authoritative)

- **Backend:** Python ≥ 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic,
  PostgreSQL, Redis, ARQ for jobs, Pydantic v2 for schemas/settings.
- **LLM access:** OpenAI Python SDK pointed at OpenRouter's base URL. The client
  must be provided through dependency injection so the provider can be swapped
  (OpenRouter ↔ OpenAI ↔ local) without touching business logic.
- **AI agent:** LangChain + LangGraph, running server-side. Streams to the
  browser. Produces per-file unified diffs; the user accepts/rejects — the agent
  never writes to documents directly.
- **Real-time:** Yjs in the browser bound to CodeMirror 6 (`y-codemirror.next`);
  `pycrdt` on the server; sync over a JWT-authenticated WebSocket.
- **LaTeX:** Tectonic. Package set controlled by one editable config file.
- **Frontend:** Vite, React, TypeScript, Tailwind, shadcn/ui (prefer ready-made
  components to avoid hand-rolled CSS bugs), CodeMirror 6, PDF.js.
- **Auth:** JWT access + refresh tokens.
- **Tests:** pytest (+ pytest-asyncio, httpx) for backend; Vitest + React
  Testing Library for frontend units; Playwright for e2e.
- **Packaging:** Docker on Alpine base images, multi-stage, lightweight.

Do not introduce alternative technologies for these roles without a spec saying
so.

## Repository conventions

- Backend lives in `backend/` (package `inkstave`, a modular monolith:
  `src/inkstave/core`, `src/inkstave/infra`, `src/inkstave/modules/<domain>`), frontend in
  `frontend/`, infra in `infra/`. The CRDT WebSocket layer runs inside the backend, in
  `backend/src/inkstave/modules/collab/`; the top-level `collab/` folder holds no code.
- Python: format with `ruff format`, lint with `ruff`, type-check with strict `mypy`
  (`make types`; run from the repository root, `mypy backend/src` reads no configuration).
  Async-first.
- TypeScript: ESLint + Prettier; strict mode on.
- Migrations: every schema change ships an Alembic migration. Never edit a
  released migration; add a new one.
- Secrets come from environment variables / `.env`; never hard-code them. An
  `.env.example` documents every variable.

## Where things are

```
backend/
  src/inkstave/
    core/           settings, database, HTTP middleware, errors, logging, observability
    infra/          Redis, cache, object storage, mailer
    modules/        admin, agent, auth, collab, compile, history, notifications, projects
    app.py router.py worker.py cli.py main.py models.py    composition root
  migrations/       Alembic
  tests/            unit/, integration/, golden/, smoke/, agent_evals/, fixtures/, factories/
  scripts/          OpenAPI export, test budget, e2e database reset
frontend/
  src/modules/      one folder per domain, with a public index.ts
  src/routes/       screens, assembled from the modules
  src/api/          generated OpenAPI types
  src/components/ src/lib/ src/i18n/
  tests/            cross-cutting Vitest suites (router, boundaries, e2e route list, contrast, CSS rules)
  e2e/              Playwright: routes.spec.ts, mobile.spec.ts, a11y.spec.ts, flows/
infra/              nginx config, Tectonic package set and sandbox image
scripts/            function-size lint, timing, dependency audit, bundle budget
tools/              docs_coverage.py (`make docs`)
docs/               system/ (the system as it is), glossary, known gaps, guides, adr/, api/
specs/              NN-slug/README.md (prompt) and spec.md (requirements)
```

## Commands

`make` with no target lists everything. The `Makefile` is the source of truth; CI runs its
targets, so what passes here passes there.

| Command | Does |
|---|---|
| `make install` | backend and frontend dependencies, from the lockfiles |
| `make up` / `make up-d` | dev stack in Docker with hot reload |
| `make docker-up` | only Postgres + Redis, for running the apps on the host |
| `make migrate` | apply migrations |
| `make lint` | ruff, format check, function and file size ceilings, import contracts |
| `make boundaries` | import contracts only |
| `make format` | ruff format |
| `make types` | strict mypy |
| `make docs` | coverage and live paths of `docs/system/` |
| `make test` | backend unit + integration |
| `make coverage` | the same, with the coverage floor |
| `make test-unit` / `make test-integration` | the two tiers as CI splits them |
| `make budget` | gate the 2-minute budget |
| `make web-types` | regenerate `docs/api/openapi.json` and `frontend/src/api/types.ts` |
| `make web-test` | eslint, prettier check, `tsc -b`, Vitest |
| `make web-coverage` | Vitest with the coverage floor |
| `make web-build` | production bundle |
| `make web-budget` | gate the initial JS of `frontend/dist` at 250 KB gzip; needs a build |
| `make e2e-infra` | throwaway Postgres + Redis for Playwright |
| `make e2e-smoke` | the in-budget Playwright tier (what CI runs) |
| `make e2e` / `make mobile` / `make e2e-flows` / `make e2e-all` | routes / 390x844 / journeys / smoke plus `@full` |
| `make up-prod` | production stack; it publishes no host port, see `docs/admin-guide.md` |

Tests for one area: `cd backend && uv run pytest tests/unit/test_x.py`,
`pnpm -C frontend exec vitest run src/modules/x`.

## Local environment

- `TEST_DATABASE_URL` must point at a disposable database: the harness drops and recreates
  it, with a suffix per xdist worker. Tests that need Postgres skip when it is unreachable.
- No test reads the machine's `.env`: `backend/tests/fixtures/env.py` isolates the
  environment before collection.
- Never run the real LLM or real Tectonic from the fast tiers. `LLM_STUB=true` and
  `COMPILE_MODE=mock` are the deterministic paths.

## Code rules

**Lint and types.** ruff with `line-length = 110`, strict mypy, at most 30 lines per function
and 300 per file (`scripts/lint_function_length.py`), cyclomatic complexity at most 6, at
most 7 arguments. Details: `~/.claude/skills/project-standard/references/lint-and-types.md`.
An ignore always carries its reason in a comment.

**Backend.** Layers go modules → infra → core, and modules follow the order in
`backend/pyproject.toml`; `make boundaries` enforces it, with a public interface in each
module's `__init__.py`. `backend/tests/unit/test_architecture.py` only lets the list of
exceptions shrink. Only the session dependency commits. Routers do HTTP only. Nothing blocks
the event loop. Every wait has a deadline. Settings come from the cached `get_settings()`.

**Frontend.** TypeScript strict. API types are generated (`make web-types`) and the generated
file is never edited. Modules are imported through their `index.ts`. Every interface string
goes through i18n, in both languages. Screens must fit 390 px. A new `fontSize` token in `tailwind.config.ts` also goes in
`frontend/src/lib/utils.ts`, or `cn` drops it as a colour.

## Tests

Pyramid: unit (no database; a unit test that uses it fails collection), integration (marker
`integration`, one transaction per test with rollback), golden (real SyncTeX and LaTeX logs),
Vitest, Playwright. A bug comes with a test. Slow work is marked `@slow` and stays out of the
default run. Details: `docs/system/overview.md`.

## Workflow

1. Read the domain's `docs/system/` file.
2. Change + test + documentation (+ glossary if there is a new term).
3. Run what you touched: `make lint types docs` + the area's tests.
4. Commit a Conventional Commit in English that describes the behavior.

**Large change** (more than ~15 files or more than one area): subagents in parallel by
disjoint files (worktrees when they edit existing code); the main agent integrates and
verifies.

## Deploy

Coolify or any Docker host, from `docker-compose.prod.yml`, with a one-shot
`inkstave migrate` before the app starts. The full variable list and boot refusals are in
`docs/admin-guide.md`. There is no `docker-compose-coolify.yml` or `docs/deploy-coolify.md`
yet (`docs/known-gaps.md`).

## Deviations from the standard

Each one is deliberate. Remove the line when the deviation ends.

| Deviation | Standard | Reason |
|---|---|---|
| Folders `backend/` and `frontend/` | `api/`, `web/` | Dockerfiles, compose files, CI, the pnpm workspace and every spec use these names; renaming buys nothing a reader needs |
| Package `inkstave` | package `api` | Console script `inkstave`, `python -m inkstave.cli` and the `arq inkstave...` worker path are typed and deployed, so the operations rule keeps them |
| `.dark` class on `<html>` | `data-theme` | Tailwind 3 `darkMode: class` and spec 59's `useApplyTheme` already use it; the rule it serves, the app's choice over the system, is met |
| `react-router-dom` | TanStack Router | Every route and the tests are built on it; a router swap is a full frontend migration with no change for users |
| Tailwind 3, Vite 5 | Tailwind 4, Vite 6 | The shadcn/ui setup and `frontend/tailwind.config.ts` are on Tailwind 3; major upgrades are a separate change with visual risk |
| `specs/NN-slug/` with `README.md` + `spec.md` | `specs/NN-name.md` | Over 100 specs already exist in this shape, separating the prompt from the requirements; specs are history |
| nginx serves the frontend | Caddy | User decision: leave as is |
| Docker left untouched for now | `docker-compose-coolify.yml`, the standard's Dockerfiles | Alignment deferred by the user; only documentation records the differences |
| `justfile` kept, as delegates to `make` | Makefile only | `just` is an accepted tool (ADR 0001) and its recipes are commands people type; the Makefile stays the source of truth |
| Alpine base images | `python:3.12-slim` | The tech stack above mandates Alpine |
| `C901` max 6 and the `PLR09xx` family | `PLR0913` only | Stricter on purpose: ADR 0106 |
| stdlib `logging` with `python-json-logger` as a dependency | structlog | Logging runs on stdlib `logging` with the project's own formatter, correlation and redaction in `backend/src/inkstave/core/observability/`; a swap changes no behavior. `python-json-logger` serves only the older `backend/src/inkstave/core/logging.py` path |
| API errors as a JSON `error` envelope | problem+json | Clients and tests depend on the envelope; it is a contract change |
| `B008` kept on, FastAPI markers listed in `extend-immutable-calls` | `Annotated` dependencies | About 276 `x = Depends(...)` sites; churning every route was not worth it in the alignment pass |

## Git commits

- Write commit messages in English following the Conventional Commits standard
  (`type(scope): subject`, e.g. `feat(auth): add JWT refresh rotation`).
- **Never add Claude Code (or any AI tool) as a co-author.** Do not append
  `Co-Authored-By` trailers or "Generated with Claude Code" lines to commits.
  Commits are authored solely by the human committer.

## Working a spec — checklist

1. Open `specs/NN-slug/README.md` (the prompt) and `spec.md` (the requirements).
2. Confirm the previous spec is fully implemented and its tests pass.
3. Study the listed Overleaf reference paths *for understanding only*.
4. Implement backend + frontend changes as specified.
5. Write the unit / integration / e2e tests the spec lists.
6. Run the full suite; ensure it passes and stays within the 2-minute budget.
7. Update `docs/` if the spec introduces an architectural decision (ADR).
8. Verify every Acceptance criterion and Definition-of-Done item.

## Refactoring specs (every 5th: 05, 10, 15, …)

These add no features. Spawn analysis over everything built so far to find bugs,
smells, dead code, missing tests, performance traps and security issues. For
each finding, *evaluate whether the fix is worth it* (risk vs. value) and apply
only the worthwhile ones, keeping all tests green. Record what was changed and
what was deliberately skipped.

## The AI agent feature (specs in the 40s)

When you implement Inkstave's own AI agent, note it has **no Overleaf
equivalent** — Overleaf has no such feature, so there is nothing to reference.
Build it from the spec. It must: run as a LangGraph graph server-side; expose
tools (search project, read file, locate a LaTeX section, propose an edit);
stream tokens and tool calls to a browser chat panel; and emit per-file unified
diffs that the user reviews and applies hunk-by-hunk. It must never mutate
project documents without explicit user confirmation.

## Where the Overleaf reference lives

The Overleaf Community Edition repo is cloned at `../overleaf/` (sibling of this
repo). Specs reference paths like `services/web/app/src/Features/...` relative to
that repo. Read-only, for understanding, under the originality rule above.
