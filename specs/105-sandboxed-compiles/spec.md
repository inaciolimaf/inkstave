# Spec 105 — Sandboxed Compiles for Public Multi-Tenant Operation (requirements)

## 1. Summary

Until now Inkstave has compiled LaTeX with the in-process `LocalTectonicRunner`:
a `tectonic` subprocess hardened with no shell-escape, a minimal secret-free
environment, a per-compile working directory, a wall-clock timeout, and
best-effort `rlimit`s. That posture is documented as **trusted-users only** — a
malicious document shares the worker's filesystem and (unless the operator
restricts it) its network.

This spec makes Inkstave safe to run for a **public, mutually-untrusted** user
base by adding a second, injectable runner — `SandboxedTectonicRunner` — that
executes each compile in a **throwaway gVisor (`runsc`) container** with:

- **no network** (`--network none`),
- a **read-only root** filesystem and a single size-capped `/tmp` tmpfs,
- **all Linux capabilities dropped** and `no-new-privileges`,
- a **non-root** user (`65534`/`nobody`),
- hard **memory / PID / CPU / tmpfs** caps enforced by the *container* (not just
  `rlimit`), and
- the user's project mounted **read-only**, outputs written to a separate mount.

Abuse is bounded by a **daily compile quota** (30/user/day → `429` +
`Retry-After`) layered on the existing per-minute limiter and per-user
concurrency cap. The runner is selected by `COMPILE_RUNNER=local|sandbox`; the
default stays `local` so existing single-tenant deployments and the whole test
suite are unaffected.

> **No Overleaf equivalent.** Overleaf CE has no compile isolation; Server Pro's
> is closed source. The sandbox runner, the offline compile image, the hardened
> daemon access, and the quota are Inkstave-internal. Nothing to copy in
> `../overleaf/`.

## 2. Context & dependencies

- **Depends on:** specs 21–23 (compile service / runner / jobs / workdir),
  52/55 (security hardening, `security/rate_limit.py`, the security checklist),
  56 (Docker/Coolify deploy), and the spec-21 pinned package set
  (`infra/tectonic/packages.toml`).
- **Target environment:** deploy via **Coolify** (Docker); isolation via
  **gVisor (`runsc`)** installed on the host and registered as a Docker runtime.
- **Unlocks:** public/multi-tenant operation. Nothing structurally depends on it;
  single-tenant deployments keep `COMPILE_RUNNER=local`.
- **Affected areas:** backend (`compile/runner.py` add-only, `config_groups.py`,
  `security/rate_limit.py`, `compile/worker.py` wiring, `api/routes/compile.py`
  one dependency), infra (`infra/tectonic/Dockerfile` + docs, compose docs),
  docs (`security-checklist.md`, `README.md`), and backend tests.

## 3. Goals

- A `SandboxedTectonicRunner` that satisfies the `TectonicRunner` protocol and
  runs each compile in an ephemeral `runsc` container with the hardening above.
- **Zero** user-controlled data in the `docker` argv; filenames validated; the
  argv is a fixed list run via `create_subprocess_exec` (no shell).
- Timeout/cancel kill the container by name (`docker kill`).
- An **offline** compile image (`inkstave-tectonic`) carrying Tectonic + the
  pinned package cache, runnable with `--network none --only-cached`.
- `docker.sock` reachable **only** from the compile worker, fronted by a
  **docker-socket-proxy** that allows just container create/start/wait/kill/rm.
- A **daily compile quota** (default 30/user/24h) returning `429` +
  `Retry-After`, plus the existing per-user concurrency cap, both configurable.
- An **agent egress lock** test that fails if any registered agent tool gains
  outbound-network capability (allow-list = only the LLM/OpenRouter client).
- Docs/README updated so **no text claims "trusted-users only"** any more; a
  **Threat model** records coverage and accepted residual risk.

## 4. Non-goals (explicitly out of scope)

- No change to `LocalTectonicRunner`, `CompileService`, or `compile/jobs.py`
  behaviour. The sandbox is purely additive and opt-in by env.
- No change to the compile API contract, response shapes, or DB schema (no
  migration). The daily quota reuses the existing `429`/`Retry-After` envelope.
- No rootless-Docker / Kubernetes / Firecracker variants (gVisor is the chosen
  isolation; the runner is parameterised enough that an operator could point it
  at another OCI runtime, but only `runsc` is specified/tested).
- No SVG/EPS/PDF output sanitisation work here — that XSS item stays open on the
  checklist and is listed as residual risk in the Threat model.

## 5. Requirements

### 5.1 — `SandboxedTectonicRunner` (the core)

- **File:** `backend/src/inkstave/compile/runner.py` (**add-only**; do not touch
  `LocalTectonicRunner`).
- Implement a new class satisfying the `TectonicRunner` `Protocol`. It runs each
  compile in an ephemeral container:

  ```
  docker run --rm --runtime=runsc --network none \
    --read-only --tmpfs /tmp:size=<N>m \
    --user 65534 --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit <P> --memory <M>m --cpus <C> \
    --name <unique-name> --workdir /work \
    -v <workdir>/input:/work:ro -v <output_dir>:/out \
    inkstave-tectonic <tectonic argv>
  ```

- **Reuse the existing tectonic argv.** Build the inner `tectonic … compile …
  --outdir /out …` argv by reusing `LocalTectonicRunner.build_command` (compose
  it; do not duplicate the flag list), passing `output_dir=/out`. Drop its env:
  the image carries the package cache, so the container needs no
  `TECTONIC_CACHE_DIR` and **no secrets**.
- **Map `ResourceLimits` to container flags.** `--memory` derives from
  `limits.address_space_bytes` (falling back to the sandbox default); `--cpus`,
  `--pids-limit`, and the `/tmp` tmpfs size come from sandbox settings (§5.4).
  These are **container** limits, not just `rlimit`s.
- **Timeout / cancel.** Reuse `timeout_s` and `CancelToken` exactly as
  `LocalTectonicRunner` does (the same `asyncio.wait` race). On timeout **or**
  cancel, `docker kill <name>` the container, then reap the `docker run` process.
  Report `RunOutcome(timed_out=…, cancelled=…)` identically.
- **Non-executing seam.** Expose a `build_command(...)` that returns the fixed
  `docker` argv (+ the generated container name) **without spawning anything**,
  mirroring `LocalTectonicRunner.build_command`. Tests assert on it.

### 5.2 — Anti-injection (critical)

- The `docker` argv is a **fixed list**; the only variable elements are: the
  validated `main_file`, host mount paths (workdir/output — not user-named), the
  generated container name, and numeric resource caps. **No file contents, no
  raw user strings, no env secrets** ever appear.
- Run with **`create_subprocess_exec` (never a shell)**; pass a minimal
  allow-listed env (`PATH`/`HOME` so `docker` resolves) — never the full
  process env.
- **Validate `main_file`** before it enters the argv: reject absolute paths,
  `..` traversal, empty/`.`/`..` segments, any segment starting with `-` (option
  injection), control characters, and anything outside a conservative charset
  (`[A-Za-z0-9._+-]`, with `/` as the only separator). On violation, fail the
  compile as a `CompileError` (mapped to `SYSTEM_ERROR`) — never run the
  container. Reuse `compile/errors.py`.

### 5.3 — Offline compile image (`inkstave-tectonic`)

- **File:** `infra/tectonic/Dockerfile` (+ a short note in `infra/README.md`).
- Multi-stage, Alpine, lightweight: install Tectonic, then **prewarm** the
  pinned package set (matching `infra/tectonic/packages.toml`, spec 21) into the
  image's Tectonic cache at build time so the container runs with
  `--network none --only-cached`.
- The image's default entrypoint is the `tectonic` binary path that the inner
  argv (§5.1) targets; it runs as the non-root `nobody` user against the
  read-only `/work` mount, writing to `/out`.
- Document the build + how the package set is kept in sync with `packages.toml`.

### 5.4 — Settings (configurable)

Add to `config_groups.py` (`CompileSettingsMixin`) with generous, public-safe
defaults, documented in `.env.example` in the neighbouring style:

- `compile_runner: Literal["local", "sandbox"] = "local"` (env `COMPILE_RUNNER`).
- `compile_sandbox_docker_bin: str = "docker"`.
- `compile_sandbox_image: str = "inkstave-tectonic"`.
- `compile_sandbox_runtime: str = "runsc"`.
- `compile_sandbox_memory_mb: int = 2048` (used when `address_space_bytes` unset).
- `compile_sandbox_cpus: float = 1.0`.
- `compile_sandbox_pids_limit: int = 256`.
- `compile_sandbox_tmpfs_mb: int = 256`.
- `rate_limit_compile_daily: str = "30/86400"` (the daily quota, §5.5).

The existing `compile_max_concurrent_per_user` (default 3) remains the per-user
concurrency cap and is already enforced in `CompileCoordinator`; it is
configurable and need not change. (An operator running fully public may lower it
to 1–2.)

### 5.5 — Anti-DoS quota

- Add a **daily compile quota**: default **30 compiles per user per 24h**,
  returning `429` + `Retry-After` when exceeded. Reuse the
  `security/rate_limit.py` named-policy pattern: register a `compile_daily`
  policy keyed on `user`, reading `rate_limit_compile_daily` from settings, and
  attach it as a second dependency on `POST …/compile` alongside the existing
  per-minute `compile` policy.
- The per-user **concurrency** cap (`compile_max_concurrent_per_user`) already
  bounds simultaneous compiles in `CompileCoordinator` and stays in force.

### 5.6 — Hardened docker-daemon access (infra docs)

- `docker.sock` is mounted **only** on the compile `worker` service — **never**
  on the public API/`backend` service. Document this in the compose/Coolify
  notes.
- Front the socket with a **docker-socket-proxy** that exposes only the verbs the
  runner needs: container **create / start / wait / kill / remove** (and image
  read). The worker talks to the proxy, not the raw socket. Provide a compose
  snippet + Coolify guidance in `infra/README.md` (and/or a sandbox doc).

### 5.7 — Agent egress lock

- Add a test that **fails if any registered agent tool** (`default_registry()`:
  `read_file`, `list_tree`, `search_project`, `locate_section`, `propose_edit`)
  acquires outbound-network capability. The allow-list of egress is **only** the
  LLM/OpenRouter client. Implement as a static guard over the
  `agent/tools/` package source: no tool module may import a network client
  (`socket`, `http.client`, `urllib.request`, `httpx`, `requests`, `aiohttp`,
  `urllib3`). Purpose: prevent a future regression that adds a URL-fetching tool
  without review.

### 5.8 — Docs & README (remove contradictory text)

- **`docs/security-checklist.md`:** turn the "Trusted-users CE caveat" into a
  **resolved** item describing the public mode (flags: `--runtime=runsc`,
  `--network none`, `--cap-drop ALL`, read-only root, non-root user, no secrets
  in env, daily quota). Keep the SVG/EPS/PDF XSS item open.
- **`README.md`:** in "Security & sandboxed compiles", **remove** the
  "Trusted-users caveat / Run Inkstave CE only for a trusted user group" text and
  replace it with the public-mode description (gVisor + ephemeral container +
  `--network none` + quota, opt-in via `COMPILE_RUNNER=sandbox`). Sweep the
  README for **any** other sentence that presupposes the trusted-users model and
  rewrite it. Leave **no contradictory text**.
- Record a **Threat model** (in `spec.md` §7 and summarised in the checklist):
  for each residual risk — gVisor escape, DoS/abuse, docker-arg injection,
  SVG/EPS/PDF XSS, authz/IDOR, supply chain — state the mitigation or the
  accepted operational risk.

## 6. Tests (fast, offline; a real container NEVER runs in CI)

> Keep the combined suite under 2 minutes. No real Docker/LaTeX/Redis; mock/stub.

- **Unit — argv shape:** `SandboxedTectonicRunner.build_command` produces an argv
  containing `--runtime=runsc`, `--network none`, `--cap-drop ALL`,
  `--memory …m`, `--pids-limit …`, `--security-opt no-new-privileges`,
  `--read-only`, `--user 65534`; the inner tectonic argv targets `/out`; and the
  argv contains **no secrets** and **no user filename outside the validated
  `main_file`** (mirror `test_compile_sandbox_no_shell_escape_no_inherited_secrets`:
  set `JWT_SECRET`/`OPENROUTER_API_KEY` in env and assert they never appear).
- **Unit — filename validation:** dangerous names (absolute, `..`, leading `-`,
  shell metacharacters, NUL/control chars) are rejected; a username-like sentinel
  never appears in the argv.
- **Unit/integration — quota:** the 31st compile in a 24h window returns `429`
  with `Retry-After`; the concurrency cap rejects the excess. (Reuse the
  rate-limit test pattern; no real sleeps.)
- **Unit — agent egress lock:** the static guard over `agent/tools/` passes today
  and would fail if a network client were imported.
- **Service tests** keep mocking the `TectonicRunner` protocol (real compile only
  in the async job, never in the fast tiers).

## 7. Threat model

| Risk | Mitigation / disposition |
| --- | --- |
| **gVisor (`runsc`) escape** | **Accepted, mitigated.** gVisor intercepts syscalls in userspace, shrinking the kernel attack surface vs. native `runc`. A `runsc` escape is the residual risk; mitigate operationally by keeping gVisor patched, running the worker on a dedicated host/VM, and pairing with `--network none` so an escapee still has no egress. |
| **DoS / abuse (compute, fork bombs, disk, output flooding)** | **Covered.** Container `--memory`, `--cpus`, `--pids-limit`, `/tmp` tmpfs size cap, the wall-clock `timeout_s` (→ `docker kill`), the spec-21 output/log/stdout byte caps, the per-user concurrency cap, and the new **daily quota** (30/user/24h → `429`). |
| **Argument injection into `docker`** | **Covered.** Fixed argv via `create_subprocess_exec` (no shell); `main_file` validated (no `..`, no leading `-`, conservative charset); file contents/names live only inside the read-only mount; no user string reaches the argv. |
| **Secret exfiltration via the compile env** | **Covered.** The container inherits no application env; the runner passes only a minimal `PATH`/`HOME`; no `TECTONIC_*`/`JWT_*`/`OPENROUTER_*` is present (asserted by test). `--network none` blocks egress even if a secret were present. |
| **XSS via SVG/EPS/PDF output** | **Open (operational).** Output sanitisation/inline-render is a frontend concern; the checklist item stays open. Compiles cannot fetch remote assets (`--network none --only-cached`), reducing the blast radius. |
| **AuthZ / IDOR** | **Covered (prior specs).** Per-project capability checks on the REST trigger and re-checked in the compile job (spec 34); no existence leak (spec 52). Unchanged here. |
| **Agent network egress** | **Covered.** Agent tools never reach the network (spec 42); the new egress-lock test prevents a regression. Only the LLM/OpenRouter client makes outbound calls. |
| **Docker daemon abuse** | **Covered (operational).** `docker.sock` only on the worker, fronted by a docker-socket-proxy limited to container create/start/wait/kill/rm; never exposed to the public API. |
| **Supply chain** | **Covered (prior specs).** `pip-audit` + `npm audit` gate (spec 57); pinned lockfiles + pinned Tectonic bundle/package set (spec 21). The compile image prewarms only the pinned set. |

## 8. Acceptance criteria

1. `SandboxedTectonicRunner` implements `TectonicRunner` and its `build_command`
   produces the fixed `docker run` argv with `--runtime=runsc`, `--network none`,
   `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`,
   `--user 65534`, `--memory`, `--pids-limit`, `--cpus`, `--tmpfs /tmp:size=…`,
   the input mount `:ro` and the output mount, and the reused tectonic argv
   targeting `/out`.
2. No secret and no user filename (beyond the validated `main_file`) ever appears
   in the argv or env (test with `JWT_SECRET`/`OPENROUTER_API_KEY` set).
3. Filename validation rejects absolute/`..`/leading-`-`/metacharacter/control
   names; the runner never spawns for such input.
4. Timeout and cancel both `docker kill` the container and report the correct
   `RunOutcome`.
5. `LocalTectonicRunner`, `CompileService`, and `compile/jobs.py` are unchanged;
   the runner is selected by `COMPILE_RUNNER` in the worker bootstrap; default is
   `local`.
6. The daily quota returns `429` + `Retry-After` on the 31st compile/24h; the
   concurrency cap rejects the excess; both numbers are settings.
7. `infra/tectonic/Dockerfile` builds an offline `inkstave-tectonic` image whose
   package set matches `packages.toml`; infra docs cover the docker-socket-proxy
   and worker-only socket.
8. The agent egress-lock test passes and would fail on a network-importing tool.
9. `docs/security-checklist.md` and `README.md` contain **no** "trusted-users
   only" claim; the public-mode description and Threat model are present.
10. `ruff`/`mypy` clean; full suite green in **< 2 minutes** (`just test-timed`).

## 9. Definition of Done

- [ ] All §5 items implemented with the smallest viable, add-only change.
- [ ] All §8 acceptance criteria pass.
- [ ] §6 tests written and green (no real container in any tier).
- [ ] `LocalTectonicRunner` / `CompileService` / `compile/jobs.py` unchanged.
- [ ] New settings in `config_groups.py` with generous defaults, documented in
      `.env.example`; runner selected by `COMPILE_RUNNER`.
- [ ] `infra/tectonic/Dockerfile` + infra docs (image, socket-proxy, worker-only
      socket) added.
- [ ] `security-checklist.md` + `README.md` carry no contradictory trusted-users
      text; §7 Threat model recorded.
- [ ] Full suite green in **< 2 minutes**; `ruff`/`mypy` clean.
- [ ] No Overleaf code copied; stack unchanged.
- [ ] Work committed on a non-`main` branch (Conventional Commits, **no** AI
      co-author) and pushed to the remote.
