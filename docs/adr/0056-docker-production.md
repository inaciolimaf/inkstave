# ADR 0056 — Docker production packaging

**Status:** accepted (spec 56) · **Phase:** 7 — Hardening, packaging & docs

## Context

Inkstave needs a production deployment that is small, restartable per-service,
and scalable per-process — the opposite of Overleaf CE's single phusion/runit
"monolith" container. Spec 56 packages the system as a few multi-stage Alpine
images orchestrated by `docker-compose.prod.yml` behind an nginx reverse proxy.

## Decisions

### One container per process (not a runit monolith)

Two source Dockerfiles produce all runtime images:

- **`inkstave-backend`** (`backend/Dockerfile`, `python:3.12-alpine`) — runs the
  API, the ARQ **worker**, and the collab WebSocket. Built **once**; the
  `backend` and `worker` services differ only by the compose **command** (no
  `INKSTAVE_PROCESS` selector env var is needed).
- **`inkstave-frontend`** (`frontend/Dockerfile`) — builds the Vite SPA on
  `node:20-alpine`, serves it on `nginx:1.27-alpine`, and reverse-proxies `/api`
  and `/ws` to the backend.

Each container is one process supervised by Docker `restart: unless-stopped` +
healthchecks — independent restarts, per-service `--scale`, smaller images.

### Collab is in-app → no separate `collab` service

The real-time specs (28/29) mount the CRDT WebSocket **inside** the FastAPI app
(`/ws/collab/...` on the same Uvicorn). So the prod compose has **no** `collab`
service and nginx routes `/ws/` → `backend:8000`. If collab is ever split into its
own process, add a `collab` service from the same image and re-point `/ws`.

### Tectonic on musl: Alpine `community` package

The backend image installs Tectonic from Alpine's `community` repository
(`apk add tectonic`) rather than a pinned static-musl release tarball. Rationale:
it is reliable and reproducible-by-Alpine-version without hand-maintaining a
download URL + SHA-256, and it is still a **single LaTeX engine, not a full TeX
Live**. The pinned static binary (`*-unknown-linux-musl` + checksum) remains the
documented alternative if a smaller/faster image or an exact version pin is
required; switching is a Dockerfile-only change. Either way, LaTeX packages are
fetched on demand into the `tectonic-cache` volume — no TeX Live tree is baked.

### Reverse proxy

nginx resolves the `backend` upstream by its compose service name on the shared
network. A `resolver` directive (with `proxy_pass` via a variable) is
**deliberately omitted**: the upstreams are static service names within the
compose network, so the addresses are stable for the container's lifetime and a
runtime DNS resolver buys nothing for the current single-network topology. If the
deployment ever moves to dynamic/rolling upstreams (e.g. an external service
discovery layer or per-deploy IP churn), add a `resolver` + variable `proxy_pass`
for restart resilience.

A single nginx server block (`infra/nginx/`): `/` serves the SPA with
`index.html` fallback (immutable cache for hashed `/assets`, no-cache for
`index.html`); `/api/` → `backend:8000` (50 MB upload cap); `/ws/` → `backend`
with `Upgrade`/`Connection: upgrade` + HTTP/1.1 and 1-hour timeouts; `/metrics`
returns 404 and is **never proxied**. `server_tokens off;`, gzip on, and the
spec-52 static security headers on SPA responses (the backend sets its own on
`/api`). TLS is the operator's job in front of the published `:80`.

### Volumes

Named, persistent: `pgdata` (Postgres), `uploads` (`/data/files`, mounted into
backend **and** worker), `tectonic-cache` (`/var/cache/tectonic`, backend +
worker). Redis runs **without** persistence (broker/cache/pub-sub; queued ARQ
jobs are best-effort across restarts) — no `redisdata` volume. Per-compile
sandbox workdirs (`/tmp/inkstave-compiles`) are **container-local and ephemeral**
— never a shared named volume. `packages.toml` is bind-mounted read-only so it
can be edited and applied with a `restart` (and is also baked into the image as a
default for standalone runs).

### Security posture

App containers run as the non-root `inkstave` user (uid/gid 10001). Only the
frontend publishes a host port; backend/worker are internal-only. No secrets are
baked into images — all config flows from `.env` (the prod compose derives
`DATABASE_URL`/`REDIS_URL` from the same `.env` values + the service hostnames),
and `.dockerignore` excludes `.env`. `ENVIRONMENT=production` is set, so the
spec-52 boot guards require a strong `JWT_SECRET` and a non-empty `CORS_ORIGINS`.

## Image-size targets

Goals (uncompressed): `inkstave-frontend` ≤ 80 MB, `inkstave-backend` ≤ 450 MB
(excluding the on-demand TeX bundle, which lives in the cache volume at runtime).
Verified in the out-of-budget CI job (spec 57), not in the fast unit suite. If a
target is exceeded, the CI job warns and reports the actual size (hard-fails only
beyond ~2×).

## Testing

Fast, in-budget assertions (`backend/tests/unit/test_docker_packaging.py`) parse
the compose, nginx, `.dockerignore`, Dockerfiles and `packages.toml`. Building and
running the images, and the size check, are the heavy CI job's responsibility
(spec 57) and are excluded from the 2-minute suite.

## Known follow-ups / exceptions

- **Workspace lockfile path:** this is a pnpm **workspace** (`pnpm-workspace.yaml`
  lists `frontend`), so the lockfile (`pnpm-lock.yaml`) and the workspace manifest
  live at the **repo root**, not under `frontend/`. The frontend Dockerfile builds
  from the repo-root context and copies the root `pnpm-lock.yaml` +
  `pnpm-workspace.yaml` (then `frontend/package.json`) before running
  `pnpm install --frozen-lockfile`, so the frozen install resolves the committed
  root lockfile and the image builds from a clean checkout. (An earlier draft
  copied `frontend/pnpm-lock.yaml*`, whose glob silently skipped the non-existent
  per-package lockfile and left the frozen install with nothing to freeze — that
  is fixed.)
- **hadolint:** apk packages are intentionally **not** version-pinned (DL3018) so
  the image picks up Alpine security updates; this is an accepted exception. The
  `# syntax` line and multi-stage layout otherwise follow hadolint guidance.
