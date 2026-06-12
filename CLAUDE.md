# CLAUDE.md — Guide for agents implementing Inkstave

This file orients any AI/automation agent (Claude Code or otherwise) working in
this repository. Read it fully before touching code.

## What this project is

Inkstave is a from-scratch, real-time collaborative LaTeX editor with a built-in
AI writing agent. It is **inspired by** Overleaf Community Edition but shares
**no code** with it. See `README.md` for the product overview and stack.

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

- Backend lives in `backend/`, frontend in `frontend/`, CRDT websocket layer in
  `collab/` (or inside `backend/` per the real-time spec), infra in `infra/`.
- Python: format with `ruff format`, lint with `ruff`, type-check with `mypy`/
  `pyright` (whichever spec 02/04 establishes). Async-first.
- TypeScript: ESLint + Prettier; strict mode on.
- Migrations: every schema change ships an Alembic migration. Never edit a
  released migration; add a new one.
- Secrets come from environment variables / `.env`; never hard-code them. An
  `.env.example` documents every variable.

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
