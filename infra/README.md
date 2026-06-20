# Inkstave infrastructure assets

`infra/` holds infrastructure and packaging assets: container build files,
docker-compose overrides, the nginx reverse-proxy config, CI helpers, the
Tectonic package set, and database init scripts. Most of these arrive in later
specs (notably the Docker/production spec, 56).

Contents:

- `postgres/` — Postgres init scripts.
- `nginx/` — the reverse-proxy config for the production frontend image.
- `tectonic/packages.toml` — the pinned LaTeX package set (spec 21).
- `tectonic/Dockerfile` — the offline `inkstave-tectonic` compile image used by
  the sandboxed runner (spec 105; see below).

## Sandboxed compiles (spec 105) — public multi-tenant operation

By default Inkstave compiles LaTeX in-process (`COMPILE_RUNNER=local`), which is
safe only when **all users of an instance trust each other**. To run Inkstave for
a **public, mutually-untrusted** audience, set `COMPILE_RUNNER=sandbox`: the
compile worker then runs every compile in a throwaway **gVisor (`runsc`)**
container with no network, a read-only root, all capabilities dropped, a non-root
user and hard memory/PID/CPU/tmpfs caps.

### 1. Host prerequisite — install gVisor

Install gVisor on the **worker host** and register `runsc` as a Docker runtime
(`/etc/docker/daemon.json` → `"runtimes": { "runsc": { "path": "/usr/local/bin/runsc" } }`,
then restart Docker). Keep `runsc` patched — a gVisor escape is the accepted
residual risk (see `docs/security-checklist.md` → Threat model).

### 2. Build the offline compile image

```sh
# from the repo root; --network=host is needed only for the cache-warmup step
docker build --network=host -f infra/tectonic/Dockerfile -t inkstave-tectonic .
```

The image bakes the pinned package set (kept in sync with
`infra/tectonic/packages.toml`) into the Tectonic cache so the per-compile
container runs fully offline (`--network none --only-cached`). When you change
`packages.toml`'s prewarm list, update the `\usepackage` list in
`infra/tectonic/Dockerfile` and rebuild.

### 3. Harden access to the Docker daemon

The runner shells out to a `docker` client. **`docker.sock` must be mounted only
on the `worker` service — never on the public `backend`/API service.** Front the
socket with a **docker-socket-proxy** that allows only the verbs the runner needs
(container create / start / wait / kill / remove, plus image read), and point the
worker at the proxy via `DOCKER_HOST`:

```yaml
# docker-compose (or a Coolify "resource") — illustrative
services:
  docker-socket-proxy:
    image: tecnativa/docker-socket-proxy
    environment:
      CONTAINERS: 1       # list/inspect
      POST: 1             # allow create/start/kill/remove (write verbs)
      IMAGES: 1           # read image metadata
      # everything else stays 0 (no EXEC, no SWARM, no VOLUMES, no NETWORKS, ...)
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    # not published to the host; reachable only on the internal compose network

  worker:
    image: inkstave-backend
    command: ["arq", "inkstave.compile.worker.WorkerSettings"]
    environment:
      COMPILE_RUNNER: sandbox
      COMPILE_SANDBOX_IMAGE: inkstave-tectonic
      DOCKER_HOST: tcp://docker-socket-proxy:2375
    # NOTE: the worker does NOT mount /var/run/docker.sock — only the proxy does.
```

On **Coolify**, deploy the worker and the socket-proxy as services in the same
project/network, set the worker's `DOCKER_HOST` to the proxy, and leave the API
service with no Docker socket at all. Pre-build `inkstave-tectonic` on each worker
host (or push it to a registry the host can pull).

The container the runner launches is fixed and contains **no** user-controlled
arguments — filenames are validated and the project is bind-mounted read-only; see
`backend/src/inkstave/compile/runner.py::SandboxedTectonicRunner`.
