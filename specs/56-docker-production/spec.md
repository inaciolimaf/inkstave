# Spec 56 — Docker Production Packaging (requirements)

## 1. Summary

This spec packages the whole system for production as a set of **small,
multi-stage, Alpine-based** Docker images — one per process — orchestrated by a
production `docker-compose.prod.yml` and fronted by an nginx reverse proxy. It
also wires the single editable LaTeX package config
(`infra/tectonic/packages.toml`). Unlike Overleaf's single phusion/runit
"monolith" container, Inkstave runs **separate lightweight containers**, which
keeps images small, restarts independent, and scaling per-service possible.

## 2. Context & dependencies

- **Depends on:** **01** (repo layout, base compose, `.env.example`), **02**
  (FastAPI app + `/health`), **03** (Postgres/Alembic), **21** (Tectonic compile
  service), **22/39/44** (ARQ worker jobs), **28/29** (collab/WS process), **09+**
  (built frontend), **51** (`/metrics` endpoint to be blocked at the proxy),
  **52** (security headers baseline).
- **Unlocks:** **57** (CI/CD builds and runs these images; migrations & bootstrap
  hook into the compose lifecycle), **58** (ops/deploy docs reference these
  files).
- **Affected areas:** infra (Dockerfiles, compose, nginx, tectonic config),
  minimal backend (a production entrypoint / process selection switch).

## 3. Goals

- One **multi-stage Alpine Dockerfile per process**: `backend` (FastAPI + ARQ
  worker + collab share the same image, different commands), and `frontend`
  (static build served by nginx). Tectonic is installed only in the backend
  image.
- A production `docker-compose.prod.yml` running: `postgres`, `redis`,
  `backend`, `worker`, `collab` (if separate process), `frontend` (nginx).
- An nginx reverse proxy routing `/` → frontend, `/api` → backend, `/ws` →
  collab WebSocket (with upgrade headers), `/metrics` → blocked (403/404).
- Healthchecks for every long-running service.
- A documented **volume strategy** (DB data, redis, uploaded files, Tectonic
  cache) and explicit ephemeral compile workdirs.
- The editable `infra/tectonic/packages.toml` wired into the backend image with a
  **minimal default** package set and clear instructions to extend it.
- Measurable **image-size targets** with a verification step.

## 4. Non-goals (explicitly out of scope)

- CI pipeline, image publishing, migrations-on-deploy, admin bootstrap → spec 57.
- Documentation prose (admin/user/architecture) → spec 58.
- Kubernetes / Helm / cloud-specific manifests (compose only here).
- TLS termination / certificates (document the hook point; leave cert issuance to
  the operator). The proxy listens on `:80` inside the network; a real
  deployment puts TLS in front of it.
- Autoscaling logic (the compose just allows `--scale`).

## 5. Detailed requirements

### 5.1 Image inventory & structure

Two source Dockerfiles produce all runtime images:

| Image | Source Dockerfile | Base | Runs |
| --- | --- | --- | --- |
| `inkstave-backend` | `backend/Dockerfile` | `python:3.12-alpine` | API (`uvicorn`), `worker` (`arq`), `collab` (uvicorn/ws) — selected by command |
| `inkstave-frontend` | `frontend/Dockerfile` | build on `node:20-alpine`, serve on `nginx:1.27-alpine` | static assets + nginx reverse proxy |

The backend image is shared by the `backend`, `worker`, and `collab` services;
they differ only by the **command** they run, so the image is built once.

### 5.2 Backend Dockerfile (`backend/Dockerfile`, multi-stage, Alpine)

**Stage 1 — `builder`** (`python:3.12-alpine`):
- Install build deps in a throwaway layer: `build-base`, `libffi-dev`,
  `postgresql-dev` (for any C extensions), plus `curl`/`tar` to fetch Tectonic.
- Install `uv`; create a virtualenv at `/opt/venv`; install **only runtime**
  dependencies from the locked `uv` lockfile (`uv sync --frozen --no-dev`).
- Do **not** copy build deps forward.

**Stage 2 — `tectonic`** (can be folded into builder): obtain a **statically
linked** Tectonic binary appropriate for musl/Alpine. Prefer the official
prebuilt `*-unknown-linux-musl` release tarball pinned by version + SHA-256
checksum; verify the checksum; place the binary at `/usr/local/bin/tectonic` and
`chmod +x`. (If a musl static build is unavailable for the pinned version, fall
back to installing `tectonic` from Alpine `community` repo via `apk`; record the
choice in the ADR. Either way the goal is a single small binary, **not** a full
TeX Live.)

**Stage 3 — `runtime`** (`python:3.12-alpine`):
- Copy `/opt/venv` from builder and `tectonic` binary from the tectonic stage.
- Install only **runtime** OS packages: `ca-certificates`, `fontconfig`, the
  minimal font set Tectonic needs, and `libpq`. No compilers.
- Create a non-root user `inkstave` (uid/gid 10001); `chown` app and writable
  dirs to it; `USER inkstave`.
- Copy application source (`backend/`) last (best layer caching). Use
  `.dockerignore` to exclude tests, caches, `.venv`, `node_modules`.
- Set `ENV PATH=/opt/venv/bin:$PATH`, `PYTHONUNBUFFERED=1`,
  `PYTHONDONTWRITEBYTECODE=1`.
- `EXPOSE 8000`.
- Default `CMD` runs the API (`uvicorn app.main:app --host 0.0.0.0 --port 8000`);
  worker and collab override the command in compose.
- A `HEALTHCHECK` hitting `GET /health` (API) — worker/collab override.

### 5.3 Frontend Dockerfile (`frontend/Dockerfile`, multi-stage, Alpine)

**Stage 1 — `builder`** (`node:20-alpine`): `pnpm install --frozen-lockfile`,
then `pnpm build` (Vite) producing `/app/dist`. Build-time env (`VITE_*`) passed
as build args.

**Stage 2 — `runtime`** (`nginx:1.27-alpine`): copy `dist/` to
`/usr/share/nginx/html`; copy the nginx config (see §5.5); run nginx as the
provided non-root nginx user where feasible; `EXPOSE 80`; `HEALTHCHECK` hitting a
lightweight `GET /healthz` location that returns `200`.

### 5.4 `docker-compose.prod.yml` (services)

| Service | Image | Command | Depends on | Healthcheck |
| --- | --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine` | default | — | `pg_isready` |
| `redis` | `redis:7-alpine` | `redis-server --save "" --appendonly no` (or persistent — see §5.6) | — | `redis-cli ping` |
| `backend` | `inkstave-backend` | uvicorn API | postgres, redis | `GET /health` |
| `worker` | `inkstave-backend` | `arq app.worker.WorkerSettings` | postgres, redis | process/`arq --check` |
| `collab` | `inkstave-backend` | uvicorn collab/WS app (or same app if not separate) | postgres, redis | WS/health endpoint |
| `frontend` | `inkstave-frontend` | nginx | backend, collab | `GET /healthz` |

Requirements:
- All app services read configuration **only** from env vars (`env_file: .env`),
  never baked into images.
- `restart: unless-stopped` on all long-running services.
- `depends_on` uses `condition: service_healthy` for DB/redis so app services
  wait for readiness.
- Only the `frontend` (nginx) publishes a host port (`80:80`, optionally
  `443:443` left for the operator's TLS front). Backend/collab are **not**
  host-published; nginx reaches them over the compose network.
- A named-volume strategy per §5.6.
- The collab service is included **only if** the real-time specs run it as a
  separate process; if collab is mounted inside the main FastAPI app, drop the
  `collab` service and route `/ws` to `backend`. The spec must support both; the
  implementer picks based on what specs 28/29 produced and records it in the ADR.

A development `docker-compose.yml` (from spec 01) continues to exist for local
dev with bind mounts and hot reload; this spec adds the **prod** file and must
not break the dev file.

### 5.5 nginx reverse-proxy config outline (`infra/nginx/nginx.conf` + `default.conf`)

A single server block on `:80`:

```
# /healthz — proxy liveness (returns 200, no upstream)
location = /healthz { access_log off; return 200 "ok\n"; }

# Static frontend (SPA): serve files, fall back to index.html
location / {
    root /usr/share/nginx/html;
    try_files $uri $uri/ /index.html;
    # long cache for hashed assets, no-cache for index.html
}

# REST API → backend
location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 50m;            # binary uploads (spec 14)
    proxy_read_timeout 65s;
}

# WebSocket (collab) → collab/backend, with upgrade headers
location /ws/ {
    proxy_pass http://collab:8000;        # or backend:8000 if not separate
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 3600s;             # long-lived sockets
    proxy_send_timeout 3600s;
}

# Block internal metrics from the public surface
location /metrics { return 404; }         # or 403; never proxied upstream
```

Additional requirements:
- A top-level `gzip on;` for text/JS/CSS/JSON; reasonable `gzip_types`.
- Security headers consistent with spec 52 (e.g. `X-Content-Type-Options`,
  `Referrer-Policy`, a CSP placeholder documented as operator-tunable). Do not
  duplicate headers the backend already sets for `/api` responses.
- `server_tokens off;`.
- Upstream names (`backend`, `collab`) resolve via Docker DNS; use variables +
  a `resolver` only if needed for restart resilience (document the choice).

### 5.6 Volume & data strategy

Named volumes:
- `pgdata` → Postgres `/var/lib/postgresql/data`.
- `redisdata` → Redis (only if persistence is enabled; default Inkstave uses
  Redis as broker/cache/pubsub, so persistence may be **off** — document the
  trade-off; queued ARQ jobs are best-effort across restarts).
- `uploads` → backend binary-file storage path (spec 14) when using the local
  disk backend; mounted into `backend` and `worker` (both may read/write).
- `tectonic-cache` → Tectonic's bundle/package cache, mounted into `backend`
  and `worker`, so package downloads are cached across compiles/restarts.

Ephemeral (no volume): per-compile sandbox workdirs (spec 21) live under a
container-local `tmpfs` or scratch dir and are cleaned per job. Document that
these must **not** be on a shared named volume.

### 5.7 Editable LaTeX package config (`infra/tectonic/packages.toml`)

- Create `infra/tectonic/packages.toml` as the **single source of truth** for the
  bundle/package configuration the compiler uses (matching the contract spec 21
  established — if spec 21 placed it elsewhere, reuse that path and do not
  duplicate; this spec only ensures it is wired into the prod image and
  documented).
- Default contents: pin the **standard Tectonic web bundle** and a minimal,
  documented set of commonly needed packages — i.e. rely on Tectonic's default
  on-demand package resolution rather than pre-bundling extras. Do **not** add
  heavy collections by default.
- The file is **copied into / mounted into** the backend image at a known path
  and read by the compile service. Changing it + rebuilding (or restarting, if
  mounted) changes available packages **without touching application code**.
- Add a clearly commented "How to add a package" section in the file itself and
  cross-reference it from the ops docs (spec 58).

### 5.8 Image-size targets (verified)

Targets (uncompressed, `docker image inspect … Size`), used as CI gates in
spec 57 and as a local check here:
- `inkstave-frontend` (nginx + static): **≤ 80 MB**.
- `inkstave-backend` (python-alpine + venv + Tectonic binary, **excluding**
  downloaded TeX bundles which land in the cache volume at runtime): **≤ 450 MB**.

If a target cannot be met, the implementer documents the actual size and the
reason in the ADR; the numbers above are goals, and the test asserts the build
succeeds and reports size (hard-failing only if grossly exceeded, e.g. >2×).

### 5.9 Configuration

Env vars (all already defined by earlier specs; this spec only ensures they flow
through compose via `.env`): `DATABASE_URL`, `REDIS_URL`, `JWT_*`,
`OPENROUTER_API_KEY`, storage path/S3 vars (spec 14), `TECTONIC_*` cache dir,
`CORS_*`, `LOG_LEVEL`. Add to `.env.example` any **new** prod-only vars this spec
introduces, e.g.:
- `INKSTAVE_PROCESS` (optional selector documented for the shared backend image),
- `TECTONIC_CACHE_DIR` (default pointing at the mounted cache volume),
- `PUBLIC_HTTP_PORT` (host port nginx publishes, default `80`).

No secrets are ever baked into an image; `.dockerignore` must exclude `.env`.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave runs separate
> lightweight Alpine containers, **not** a single phusion/runit image, so treat
> these as background only.

- `server-ce/Dockerfile`, `server-ce/Dockerfile-base` — how Overleaf layers its
  monolith image and installs TeX/runtime deps. Inkstave splits per-process and
  uses a Tectonic binary instead of full TeX Live.
- `server-ce/Makefile` — build/tag/push targets; informs the local build helper.
- `server-ce/nginx/` (`nginx.conf.template`, `overleaf.conf`,
  `clsi-nginx.conf`) — reverse-proxy and upload-size patterns, WebSocket upgrade
  handling, static serving. Inkstave writes its own minimal config.
- `server-ce/runit/` — how Overleaf supervises many processes in one container.
  Inkstave intentionally avoids this: one process per container, supervised by
  Docker `restart` + healthchecks.
- `docker-compose.yml` (repo root) — service wiring/volumes ideas only.

## 7. Acceptance criteria

1. **Given** a clean checkout, **when** I run the backend image build, **then** it
   completes using a multi-stage `python:3.12-alpine`-based Dockerfile and the
   final image contains the Tectonic binary and a non-root default user.
2. **Given** the frontend image build, **when** it completes, **then** the runtime
   stage is `nginx:1.27-alpine` serving the Vite `dist/` and contains no Node
   toolchain.
3. **Given** `docker compose -f docker-compose.prod.yml up`, **when** all services
   start, **then** `postgres`, `redis`, `backend`, `worker`, `frontend` (and
   `collab` if separate) reach a healthy state via their healthchecks.
4. **Given** the stack is up, **when** I `GET http://localhost/` , **then** nginx
   serves the SPA `index.html`; **when** I `GET /api/health`, **then** it proxies
   to the backend and returns the health payload.
5. **Given** the stack is up, **when** a client opens a WebSocket to `/ws/...`,
   **then** nginx forwards it with `Upgrade`/`Connection` headers and the socket
   stays open (no immediate close/426).
6. **Given** the stack is up, **when** I `GET /metrics` through the public proxy,
   **then** I receive 404/403 and the request is **not** forwarded to any
   upstream.
7. **Given** the prod compose, **when** I inspect it, **then** only the frontend
   publishes a host port; backend/collab are reachable only on the internal
   network; all app services load config from `.env` and none bake secrets.
8. **Given** named volumes, **when** the stack restarts, **then** Postgres data,
   uploaded files, and the Tectonic cache persist, while per-compile workdirs do
   not.
9. **Given** `infra/tectonic/packages.toml`, **when** I edit it and rebuild (or
   restart, if mounted), **then** the compiler uses the new package config with
   **no** application-code change, and the file documents how to add packages.
10. **Given** a successful build, **when** I inspect image sizes, **then** the
    frontend and backend images are within (or the report explains any deviation
    from) the §5.8 targets, and the backend image contains **no** full TeX Live
    tree.
11. **Given** any app container, **when** I check its runtime user, **then** it
    runs as the non-root `inkstave` user.

## 8. Test plan

> Image builds are **not** part of the 2-minute unit budget; they run in a
> dedicated CI job (spec 57). The fast tests here are config-level assertions.

- **Unit / static (fast, in-budget):**
  - A test that **parses** `docker-compose.prod.yml` (YAML) and asserts: services
    present, only frontend publishes a host port, `restart` policies set,
    healthchecks defined, `env_file` used, no inline secret values, expected
    volumes declared.
  - A test that reads the nginx config and asserts the presence/shape of the
    `/api`, `/ws` (with `Upgrade`/`Connection upgrade` + `proxy_http_version
    1.1`), `/metrics` (returns 404/403, no `proxy_pass`), and SPA fallback
    blocks; `server_tokens off;`; gzip on.
  - A test that asserts `.dockerignore` excludes `.env`, tests, caches, and
    `node_modules`/`.venv`.
  - A test asserting `infra/tectonic/packages.toml` exists, parses as TOML, and
    contains the "how to add a package" comment marker.
- **Integration (separate CI job, out-of-budget):**
  - Build both images; run `docker compose -f docker-compose.prod.yml up -d`;
    poll healthchecks until healthy or timeout; assert `/`, `/api/health`,
    `/ws` upgrade, and `/metrics` blocked behave per §7; tear down.
  - Assert image sizes via `docker image inspect` against §5.8 (soft gate:
    warn/explain; hard-fail only at >2× target).
- **E2E (Playwright):** none added here (the e2e suite from spec 54 may
  optionally be pointed at the prod compose in the out-of-budget job, but that is
  not required by this spec).
- **Performance/budget note:** all in-budget tests are pure file parsing/string
  assertions (milliseconds). Anything that builds or runs containers is isolated
  to the heavy CI job and excluded from the 2-minute suite.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green (fast tests in-budget; heavy job defined).
- [ ] Full (fast) suite still runs in < 2 minutes.
- [ ] Lint/format/type-check clean; Dockerfiles pass `hadolint` (or documented
      exceptions).
- [ ] New prod-only env vars documented in `.env.example`.
- [ ] ADR added under `docs/` (one-container-per-process, Tectonic-on-musl,
      image-size targets, collab-separate-vs-inline decision).
- [ ] No Overleaf code or config copied.
