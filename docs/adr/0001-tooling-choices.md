# ADR 0001 — Tooling choices: `uv`, `pnpm`, `just`

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 01 — Project Scaffolding

## Context

Inkstave is a polyglot monorepo: a Python (FastAPI) backend and a
TypeScript (Vite/React) frontend, plus infrastructure orchestrated with Docker
Compose. The scaffolding spec must pick the Python package manager, the Node
package manager, and a cross-language command runner. These choices are made
once here and inherited by every later spec, so they need to be fast,
reproducible, and low-friction for both humans and automation agents.

## Decision

### Python dependency management: `uv`

We use [`uv`](https://docs.astral.sh/uv/) as the Python package and project
manager (declared in `backend/pyproject.toml`, with a committed `uv.lock`).

- Extremely fast resolution and installs, which matters for the hard
  < 2-minute test-suite budget and for CI.
- Single tool that replaces `pip`, `pip-tools`, `virtualenv`, and `pyenv`-style
  Python version handling; `requires-python = ">=3.12"` is enforced.
- First-class support for PEP 735 `[dependency-groups]`, letting later specs
  append `dev`/test/type-checking deps cleanly.
- A committed lockfile gives deterministic, reproducible environments.

### Node dependency management: `pnpm`

We use [`pnpm`](https://pnpm.io/) (pinned via the `packageManager` field in
`frontend/package.json`, with a root `pnpm-workspace.yaml`).

- Content-addressed store → fast installs and minimal disk use, again helping
  the test budget and CI.
- Strict, non-flat `node_modules` prevents accidental reliance on undeclared
  (phantom) dependencies.
- Native workspaces support; today there is a single `frontend` package, but
  the workspace leaves room to grow without re-tooling.

### Command runner: `just`

We use [`just`](https://github.com/casey/just) as the task runner (`justfile`
at the repo root).

- Simple, declarative recipes — easier to read and maintain than a `Makefile`
  full of `.PHONY` targets and shell escaping quirks.
- Language-agnostic: it can drive `uv`, `pnpm`, and `docker compose` from one
  place, giving humans and agents a single, discoverable entry point
  (`just --list`).
- No hidden build-graph semantics; recipes are just commands, which is exactly
  what this project needs.

## Consequences

- Contributors need `uv`, `pnpm`, and `just` installed locally; the README and
  `just bootstrap` document the setup path.
- Lockfiles (`uv.lock`, `pnpm-lock.yaml`) are committed and must not be
  git-ignored.
- Later specs extend, but do not replace, these choices; introducing an
  alternative tool for any of these roles requires a new ADR.

## Alternatives considered

- **Python:** Poetry / PDM / plain pip + venv — all viable, but slower and/or
  more ceremony than `uv`, which now covers the same ground.
- **Node:** npm / Yarn — npm is slower with a flat `node_modules`; Yarn is what
  Overleaf uses, but `pnpm`'s strictness and speed fit Inkstave better.
- **Runner:** `make` / npm scripts / shell scripts — `make` is ubiquitous but
  awkward for non-build tasks; `just` is purpose-built for this.
