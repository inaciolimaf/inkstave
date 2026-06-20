# ADR 0021 — Compile sandbox & security model (Tectonic)

- **Status:** Accepted (the "trusted-users" caveat is **superseded by spec 105**)
- **Date:** 2026-06-09
- **Context spec:** 21 — Tectonic Integration (compile service)

> **Update (spec 105).** The trusted-users caveat below describes the default
> in-process `local` runner. Spec 105 adds an opt-in `sandbox` runner
> (`COMPILE_RUNNER=sandbox`) that isolates each compile in a gVisor (`runsc`)
> container with no network, dropped capabilities and hard resource caps, making
> Inkstave safe for **public, mutually-untrusted** users. See
> `docs/security-checklist.md` (Threat model) and `infra/README.md`.

## Context

Inkstave compiles user-supplied LaTeX. LaTeX is a Turing-complete macro language
and TeX engines historically support **shell-escape** (running arbitrary
shell commands) and can exhaust CPU/memory/disk. The compile service must run
untrusted input while bounding the blast radius. We use **Tectonic** (a single
static Rust binary that fetches + caches packages on demand) rather than a full
TeX Live + `latexmk` install, which keeps the engine layer to one process and
suits Alpine images.

## Decisions (the security model)

### 1. Per-compile isolated workdir (mode 0700)

Each compile gets a fresh `<COMPILE_WORKDIR_ROOT>/<compile_id>/` with `input/`
and `output/` subdirs, created **0700**. Outputs go to a **dedicated `output/`
dir** (not compiled in place), so output discovery is a trivial walk — no
input/output diffing. The workdir is **always removed** in a `finally`
(success / failure / timeout / cancel / system-error), unless `keep_workdir`
(debug) or `COMPILE_KEEP_WORKDIR_ON_FAILURE` is set.

### 2. Strict path safety on assembly

Every document/file is materialised through `safe_join`, which rejects
**absolute paths, `..` traversal, and symlink escapes** (the deepest existing
ancestor must resolve back inside the workdir). Any violation fails the whole
compile with `SYSTEM_ERROR` and writes nothing outside the tree. (The file-tree
spec already prevents such names; this is defence in depth.)

### 3. No shell, ever

The real `LocalTectonicRunner` spawns Tectonic with
`asyncio.create_subprocess_exec(*argv, ...)` — an **argument vector, never a
shell string**, no `shell=True`, no interpolation. Tectonic is invoked with
shell-escape **disabled** (it is not enabled; we never pass `-Z shell-escape`).

### 4. Bounded resources

- **Wall-clock timeout** (`TECTONIC_COMPILE_TIMEOUT_S`): the runner SIGTERMs the
  process on expiry, then SIGKILLs after a short grace, and returns `TIMEOUT`.
- **Cooperative cancellation** via `CancelToken` (SIGTERM/SIGKILL on cancel).
- **Input bounds** (`COMPILE_MAX_INPUT_FILES` / `_BYTES`) are validated **before**
  spawning the engine.
- **Output/log/stdout caps** (`COMPILE_MAX_OUTPUT_BYTES`, `_LOG_BYTES`,
  `_STDOUT_BYTES`) truncate captured data (`truncated` flag set).
- **Best-effort POSIX rlimits** on the child (`RLIMIT_CPU`, `RLIMIT_AS`) via
  `preexec_fn`. These are *best-effort*, **not** a substitute for container
  limits.

### 5. Network policy

`infra/tectonic/packages.toml` + env (`TECTONIC_OFFLINE`,
`[policy].allow_network_fetch`) control whether a compile may fetch uncached
packages. The cache lives at `TECTONIC_CACHE_DIR` (a persistent volume); a build
step can **prewarm** the declared package set so offline first-compiles work.
Hardened deployments set offline/`allow_network_fetch=false`.

### 6. The explicit CE-style "trusted users" caveat

A single Tectonic process bounded by best-effort rlimits is **not a hard
security boundary on its own.** Like Overleaf Community Edition, Inkstave's
threat model assumes **trusted collaborators**: only users you trust should be
able to submit arbitrary LaTeX to a project. The real isolation boundary is the
**container** the backend (and thus Tectonic) runs in — CPU/memory/PID/network
limits, a read-only root FS where possible, a non-root user, and a tmpfs/quota
on `COMPILE_WORKDIR_ROOT`. Inkstave disables shell-escape and bounds resources
in-process, but the **residual risk** (resource exhaustion, package-fetch
side effects when network is allowed) is mitigated by, not eliminated without,
container isolation. Multi-tenant untrusted compiling would require a stronger
sandbox (per-compile container / gVisor / seccomp) — out of scope here.

## Consequences

- New module `backend/src/inkstave/compile/` (no DB tables); the service is
  constructed via DI so spec 22 (ARQ job + API) and spec 23 (output persistence)
  reuse it. The runner is an injected `Protocol` so tests substitute a
  `FakeRunner` — the default suite runs **zero real compiles**.
- New settings (`TECTONIC_*`, `COMPILE_*`) in `.env.example`;
  `infra/tectonic/packages.toml` is the editable package config.
- The Dockerfile must install a pinned Tectonic and mount `TECTONIC_CACHE_DIR`;
  staged here, finalised in the Docker spec (56). A real one-line compile is
  covered by an **opt-in** smoke test (`RUN_REAL_COMPILE=1`).

## Alternatives considered

- **TeX Live + latexmk (Overleaf's CLSI model)** — heavier image, many moving
  parts; rejected for Tectonic's single self-contained binary.
- **Per-compile Docker container** — stronger isolation but heavy and
  operationally complex; deferred (the container around the backend is the
  boundary for the trusted-users model).
