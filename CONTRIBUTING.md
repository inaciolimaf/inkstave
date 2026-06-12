# Contributing to Inkstave

Thanks for helping build Inkstave! This guide covers local setup, the test
budget, the spec-driven workflow, conventions, and — most importantly — the
**originality rule**.

## Development setup

**Prerequisites:** Docker, Python ≥ 3.12 with [`uv`](https://docs.astral.sh/uv/),
Node 20 with [`pnpm`](https://pnpm.io/).

```bash
cp .env.example .env                       # dev defaults are safe out of the box

# Infrastructure (Postgres + Redis) for local dev:
docker compose up -d                       # the dev compose (NOT the prod one)

# Backend (runs on the host against the dev infra):
cd backend && uv sync
uv run alembic upgrade head                # or: uv run inkstave migrate
uv run uvicorn inkstave.main:app --reload

# Frontend:
cd frontend && pnpm install
pnpm dev
```

The collaboration WebSocket runs inside the backend process. The AI agent and
LaTeX compiles run in the ARQ worker: `uv run arq inkstave.compile.worker.WorkerSettings`.

## Running the test suite

```bash
# Backend (unit + integration; needs the dev Postgres). -n auto for parallel.
cd backend && uv run pytest                # add -n auto to parallelize
# Frontend unit tests:
cd frontend && pnpm test
# End-to-end (real-stack smoke; see docs/e2e-strategy.md):
docker compose -f docker-compose.test.yml up -d
cd frontend && pnpm exec playwright test --project=smoke
```

**The 2-minute budget is a hard rule.** The whole suite (unit + integration +
e2e) must finish in **under 120 seconds**; CI measures and enforces it
(`backend/scripts/check_test_budget.py`). Slow work (LaTeX/LLM) belongs in async
jobs and must be stubbed in the fast tiers. Mark genuinely heavy tests `@slow`
(excluded by default).

### Lint / format / type-check

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src
cd frontend && pnpm lint && pnpm format:check && pnpm typecheck
```

When you change an API endpoint or schema, regenerate the committed OpenAPI
artifact: `cd backend && uv run python scripts/export_openapi.py` (a test fails on
drift).

## The spec-driven workflow

Inkstave is built by implementing the numbered specs in [`specs/`](specs/README.md)
**in order**. Each `specs/NN-slug/` has a `README.md` (the prompt) and a `spec.md`
(authoritative requirements + test plan). Implement a spec fully — code **and**
its tests — until every **Definition of Done** and **Acceptance criterion** passes,
then move to the next. **Every 5th spec (05, 10, …) is a refactoring pass**: no new
features, just bug-fixing, de-flaking and hardening, recorded under
[`docs/refactors/`](docs/refactors/).

## Conventions

- **Backend:** async-first; format with `ruff format`, lint with `ruff`,
  type-check with `mypy` (strict). Every schema change ships an Alembic migration
  (never edit a released one — add a new one). Reach settings through the cached
  `get_settings()`; never read `os.environ` in request code.
- **Frontend:** TypeScript strict; ESLint + Prettier; prefer ready-made
  **shadcn/ui** components over hand-rolled CSS.
- **Secrets** come from env / `.env` (git-ignored) — never hard-code them;
  `.env.example` documents every variable.
- Design decisions are recorded as ADRs under [`docs/adr/`](docs/adr/).

## Originality — no Overleaf code (read this)

Inkstave is **MIT**-licensed and must stay that way. Overleaf Community Edition is
**AGPLv3**. Therefore:

- **Never copy, paste, or mechanically translate Overleaf source code, config, or
  documentation** into Inkstave.
- You may *read* the Overleaf repo (cloned at `../overleaf/`) only to **understand**
  an approach — treat it as a textbook, not a clipboard.
- Every line of Inkstave must be your own independent implementation.

By opening a pull request you affirm that **all code in it is original work** and
that **no Overleaf (or other AGPL/incompatible) code was copied**. State this in
the PR description.

## Pull-request checklist

- [ ] Tests added/updated and **green**; the suite stays **under 2 minutes**.
- [ ] `ruff` / `mypy` / `eslint` / `tsc` clean; formatting checked.
- [ ] Docs updated if behavior/config changed (and `docs/api/openapi.json`
      regenerated for API changes).
- [ ] An Alembic migration accompanies any schema change.
- [ ] **No Overleaf code copied** — original work affirmed.
