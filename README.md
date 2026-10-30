# Inkstave

> An open-source, real-time collaborative LaTeX editor with a built-in AI writing agent.

Inkstave is a from-scratch system **inspired by** [Overleaf Community Edition](https://github.com/overleaf/overleaf).
It is **not** a fork and shares **no source code** with Overleaf. The Overleaf
codebase is used only as a *reference for understanding architecture and
behaviour* — every line of Inkstave is written independently (Inkstave is MIT
licensed; see [`LICENSE`](LICENSE)).

---

## What Inkstave does

- ✍️ **Edit LaTeX in the browser** with a modern code editor (CodeMirror 6).
- 📄 **Compile to PDF** quickly using the [Tectonic](https://tectonic-typesetting.github.io/) engine, with a PDF preview, log/error annotations, and SyncTeX.
- 👥 **Collaborate in real time** — two or more people editing the same document
  live, with presence and cursors, powered by CRDTs (Yjs + pycrdt). Share as
  owner / editor / viewer.
- 🕑 **Version history** — snapshot, diff, label and restore previous versions.
- 🤖 **AI writing agent** — a full agentic harness (LangGraph) that can search
  your project, locate sections (e.g. "the introduction"), and propose edits as
  reviewable diffs. **Nothing is applied without your explicit approval.**

## Quickstart

**Prerequisites:** Docker + Docker Compose.

```bash
git clone <this-repo> && cd inkstave
cp .env.example .env
# Edit .env: set a strong JWT_SECRET, your CORS_ORIGINS, and OPENROUTER_API_KEY
# (the AI agent); set ENVIRONMENT=prod for a real deployment.

docker compose -f docker-compose.prod.yml build

# First run: migrate, then create the first admin (idempotent). With the default
# MIGRATE_ON_START=false the backend refuses to start on an unmigrated database.
docker compose -f docker-compose.prod.yml run --rm backend python -m inkstave.cli migrate
docker compose -f docker-compose.prod.yml run --rm \
  -e INKSTAVE_ADMIN_EMAIL=you@example.com -e INKSTAVE_ADMIN_PASSWORD='change-me' \
  backend python -m inkstave.cli bootstrap-admin

docker compose -f docker-compose.prod.yml up -d
```

**`docker-compose.prod.yml` publishes no host port.** The `frontend` container only
exposes port 80 on the compose network, for a managed proxy such as Coolify or Traefik
to route a domain to it, and `PUBLIC_HTTP_PORT` is not read. To open it on
`http://localhost` without a proxy, add a `ports` mapping in a compose file of your own:
see [Deployment](docs/admin-guide.md#deployment). Put TLS in front of it for a public
deployment. The full first-run flow, scaling, backups and troubleshooting are in the
[Admin Guide](docs/admin-guide.md).

For **local development**, `make up` runs everything in Docker with hot reload on
http://localhost:5173. To run the apps on the host instead, see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Where things are

```
backend/              FastAPI app (package `inkstave`), Alembic migrations, pytest suites
  src/inkstave/
    core/             settings, database, HTTP, errors, logging, observability
    infra/            Redis, cache, object storage, mailer
    modules/          admin, agent, auth, collab, compile, history, notifications, projects
    app.py, router.py, worker.py, cli.py    composition root
frontend/             Vite + React SPA
  src/modules/        one folder per domain, with a public index.ts
  src/routes/         screens, assembled from the modules
  e2e/                Playwright: routes, mobile, flows/
infra/                nginx config, Tectonic package set and sandbox image
scripts/, tools/      lint, timing, audit and documentation checks
docs/                 guides, docs/system/ (the system as it is), ADRs, OpenAPI artifact
specs/                what was asked and why, one folder per spec
Makefile              every command; `make` lists them
```

## Commands

```bash
make                  # list every command
make install          # backend and frontend dependencies, from the lockfiles
make up               # dev stack in Docker with hot reload (Ctrl+C stops it)
make docker-up        # only Postgres + Redis, for running the apps on the host
make migrate          # apply database migrations
make lint types docs  # backend lint, strict mypy, documentation check
make test             # backend unit + integration
make web-test         # frontend lint, format check, tsc and Vitest
make e2e-infra e2e-smoke  # Playwright smoke tier
make up-prod          # production stack (see the note on host ports above)
```

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend API | Python · **FastAPI** |
| ORM / migrations | **SQLAlchemy** · **Alembic** |
| Database | **PostgreSQL** |
| Cache / pub-sub / queue broker | **Redis** |
| Async jobs | **ARQ** |
| Real-time collaboration | **Yjs** (browser) + **pycrdt** (server) over WebSocket |
| LaTeX engine | **Tectonic** |
| AI agent | **LangGraph** + OpenAI SDK pointed at **OpenRouter** (swappable via DI) |
| Frontend | **Vite** · **React** · **TypeScript** · **Tailwind** · **shadcn/ui** · **CodeMirror 6** · **PDF.js** |
| Auth | **JWT** (access + refresh) |
| Tests | **pytest** (backend) · **Vitest** (frontend) · **Playwright** (e2e) |
| Packaging | **Docker** (Alpine, multi-stage) · docker-compose |

## Documentation

Everything lives under [`docs/`](docs/README.md):

- **[User Guide](docs/user-guide.md)** — editing, compiling, history,
  collaboration, and the AI agent.
- **[System documentation](docs/system/README.md)** — how each domain works today,
  written from the code. Start here to change the system.
- **[Glossary](docs/glossary.md)** — domain terms, code names and the Portuguese
  product terms.
- **[Known gaps](docs/known-gaps.md)** — what is knowingly unfinished, and why.
- **[Admin / Operations Guide](docs/admin-guide.md)** — deploy, the full env-var
  reference, bootstrap, scaling, backups, LaTeX packages, observability, upgrades,
  troubleshooting.
- **[Architecture](docs/architecture.md)** — services, data-flow diagrams, the
  data model, and ADRs.
- **[API Reference](docs/api-reference.md)** — the OpenAPI schema and how to view
  the live docs.
- **[CONTRIBUTING](CONTRIBUTING.md)** — dev setup, the test budget, the
  spec-driven workflow, and the no-Overleaf-code rule.

## Building Inkstave (spec-driven)

Inkstave is built by implementing the specifications in [`specs/`](specs/README.md)
**strictly in numerical order**; each folder has a `README.md` (the prompt) and a
`spec.md` (requirements + test plan). Every 5th spec is a **refactoring** pass. The
table of every spec and what it decides is the [roadmap](specs/README.md#the-roadmap).

## Performance & testing budget

A hard project constraint: **the entire test suite (unit + integration + e2e)
must run in under 2 minutes.** Long-running work (LaTeX compiles, AI agent runs)
is pushed to async ARQ jobs and is mocked/stubbed in the fast test tiers. CI
measures and enforces this gate.

## Security & sandboxed compiles

Inkstave supports two compile postures, selected by `COMPILE_RUNNER`:

- **`local` (default).** Tectonic runs in a subprocess with process-level hardening
  (no shell-escape, a per-compile working directory that is cleaned up, a CPU
  timeout, and a minimal environment that carries **no application secrets**). Best
  for a single team / trusted group.
- **`sandbox` (public multi-tenant).** Every compile runs in a **throwaway
  gVisor (`runsc`) container** with `--network none`, a read-only root, all Linux
  capabilities dropped, `no-new-privileges`, a non-root user and hard
  container-enforced memory/PID/CPU/tmpfs caps. The project is mounted read-only,
  no application secrets reach the container. In both postures abuse is bounded by a
  **daily compile quota** (30 requests per user per fixed 24-hour window) and a
  per-user concurrency cap. It is designed for **public, mutually-untrusted** users,
  but it has not been proven on a real deployment: see
  [known gaps](docs/known-gaps.md#compile-sandbox). Operate it by installing gVisor on the worker host, building the offline `inkstave-tectonic`
  image, and exposing the Docker socket only to the worker via a socket-proxy —
  see [infra/README.md](infra/README.md).

The compile sandbox never lets user-controlled data into the container's launch
arguments (filenames are validated; the project is bind-mounted read-only), and
the AI agent's tools have **no network egress** (only the LLM provider client
makes outbound calls). The accepted residual risk in `sandbox` mode is a gVisor
escape — mitigated by keeping `runsc` patched and pairing it with `--network
none`. Full details and the threat model are in
[docs/security-checklist.md](docs/security-checklist.md).
