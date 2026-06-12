# Spec 21 — Tectonic Integration (requirements)

## 1. Summary

This spec delivers the **synchronous compile service**: a self-contained backend
module that assembles all of a project's files (documents from spec 13, binary
files from spec 14) into a freshly-created, isolated working directory, invokes
the **Tectonic** engine to produce a PDF, captures stdout/stderr and the LaTeX
`.log`, enforces wall-clock timeouts and resource limits, and cleans up
afterwards. It exposes one pure-ish service function — no HTTP, no queue, no
output persistence (those are specs 22 and 23). Tectonic is chosen because it is
a single static Rust binary that fetches the packages it needs on demand and
caches them, which suits Alpine images and keeps the engine layer simple.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 13** (`document-content-api`) — provides the document content store
    and a way to read every text document of a project with its path.
  - **Spec 14** (`binary-file-storage`) — provides the storage abstraction
    (`Storage` interface, disk and S3-compatible backends) used to fetch binary
    files (images, `.bib`, fonts, etc.) into the workdir.
  - **Spec 02** (backend foundation) — settings, structured logging, error
    types, app factory.
- **Unlocks:**
  - **Spec 22** — wraps this service in an ARQ job and a compile API.
  - **Spec 23** — persists the outputs this service produces.
  - **Specs 26, 27** — synctex output and log parsing build on the artifacts
    produced here (`.synctex.gz`, `.log`).
- **Affected areas:** backend (`backend/app/compile/`), infra
  (`infra/tectonic/packages.toml`, Dockerfile Tectonic install), docs (ADR).

## 3. Goals

- A `CompileService.compile(...)` coroutine that, given a project id and compile
  options, returns a structured result describing success/failure, the path to
  the produced PDF inside the workdir, the captured log, stdout/stderr, exit
  status, and timing.
- Deterministic **workdir assembly**: every project document and binary file is
  materialised at its correct relative path under a unique temp root.
- **Tectonic invocation** through an injectable runner abstraction so tests can
  stub it; the real runner shells out to the `tectonic` binary.
- **Timeout enforcement**: a hard wall-clock limit kills the process and returns
  a `timeout` outcome rather than hanging.
- **Resource limits**: bounded output size, bounded number/size of input files,
  and (where the platform supports it) CPU/memory limits on the child process.
- **Isolation / sandbox**: each compile runs in its own directory tree; document
  the security model and its caveats explicitly (CE-style "trusted users").
- **Guaranteed cleanup** of the workdir on success, failure, timeout and
  cancellation, with an optional "keep on failure for debugging" flag.
- An **editable package config** at `infra/tectonic/packages.toml` plus a
  documented Tectonic bundle/cache strategy so a deployer can add packages
  without touching code.

## 4. Non-goals (explicitly out of scope)

- HTTP endpoints, request validation, debouncing, concurrency queues, ARQ — all
  spec 22.
- Persisting/serving the PDF, log, synctex or aux artifacts — spec 23.
- Parsing the log into structured diagnostics or editor annotations — spec 27.
- SyncTeX forward/inverse resolution — spec 26.
- Multi-engine support (lualatex/xelatex selection UI). Tectonic is the only
  engine; it internally uses an XeTeX-derived engine. Engine choice is fixed.
- Incremental/cached compiles, content-addressed caches, draft mode.

## 5. Detailed requirements

### 5.1 Data model

This spec introduces **no database tables**. All state lives on the filesystem
for the duration of a compile and in the returned result object. (Compile
records and output metadata are introduced by specs 22 and 23.)

### 5.2 Backend / service contracts

All code lives under `backend/app/compile/`. Suggested layout:

```
backend/app/compile/
├── __init__.py
├── service.py          # CompileService — the public entry point
├── workdir.py          # workdir creation, assembly, cleanup
├── runner.py           # TectonicRunner protocol + real implementation
├── limits.py           # ResourceLimits, timeout helpers
├── packages.py         # loads infra/tectonic/packages.toml
├── result.py           # CompileResult / CompileOutcome dataclasses & enums
└── errors.py           # compile-specific exceptions
```

#### 5.2.1 Result types (`result.py`)

```python
from enum import StrEnum
from dataclasses import dataclass, field
from pathlib import Path

class CompileStatus(StrEnum):
    SUCCESS = "success"          # PDF produced, exit code 0
    FAILURE = "failure"          # engine ran but produced no usable PDF
    TIMEOUT = "timeout"          # killed by wall-clock limit
    CANCELLED = "cancelled"      # cooperatively cancelled before/while running
    SYSTEM_ERROR = "system_error"  # workdir/runner/IO failure unrelated to LaTeX

@dataclass(slots=True)
class CompileArtifact:
    name: str          # e.g. "output.pdf", "main.log", "main.synctex.gz"
    rel_path: str      # path relative to the workdir output root
    abs_path: Path
    size_bytes: int
    content_type: str  # "application/pdf", "text/plain", "application/gzip", ...

@dataclass(slots=True)
class CompileResult:
    status: CompileStatus
    pdf: CompileArtifact | None          # None unless a PDF was produced
    log_text: str                        # contents of the LaTeX .log (may be "")
    stdout: str                          # captured tectonic stdout (truncated)
    stderr: str                          # captured tectonic stderr (truncated)
    exit_code: int | None                # process exit code, None if never spawned
    duration_ms: int                     # wall-clock of the engine run
    artifacts: list[CompileArtifact] = field(default_factory=list)  # all output files
    workdir: Path | None = None          # populated only when keep_workdir is set
    truncated: bool = False              # True if any captured stream was clipped
```

#### 5.2.2 Compile options (`service.py`)

```python
@dataclass(slots=True)
class CompileOptions:
    project_id: UUID
    main_file: str = "main.tex"   # path, relative to project root, of the root document
    timeout_s: int | None = None  # None → settings default (TECTONIC_COMPILE_TIMEOUT_S)
    keep_workdir: bool = False    # debug: do not delete workdir; populate result.workdir
    compile_id: UUID | None = None  # optional correlation id (supplied by spec 22)
```

#### 5.2.3 The runner abstraction (`runner.py`)

The service MUST NOT call `tectonic` directly; it goes through an injected
runner so unit/integration tests can substitute a fake. Define a `Protocol`:

```python
class TectonicRunner(Protocol):
    async def run(
        self,
        *,
        workdir: Path,
        main_file: str,
        output_dir: Path,
        timeout_s: int,
        limits: ResourceLimits,
        cancel: CancelToken,
    ) -> RunOutcome: ...
```

`RunOutcome` is a small dataclass: `exit_code: int | None`, `stdout: str`,
`stderr: str`, `timed_out: bool`, `cancelled: bool`, `duration_ms: int`.

The **real** implementation (`LocalTectonicRunner`) builds the argument vector
for the `tectonic` binary and runs it with `asyncio.create_subprocess_exec`
(never `shell=True`; never string interpolation into a shell). Required Tectonic
behaviour to configure via flags/env (verify against the installed Tectonic
version at implementation time; these are the intended semantics):

- Compile the given `main_file` to PDF.
- Write all outputs to `output_dir` (kept separate from inputs so output
  discovery is trivial — contrast with Overleaf, which compiles in place and
  must *diff* inputs vs. outputs).
- Emit the SyncTeX file (gzipped) and keep intermediate `.log`/`.aux` so later
  specs can use them.
- Use the **offline/pinned bundle** configured in §5.5 so a compile never
  reaches out to the network unless explicitly allowed.
- Point Tectonic's package cache at `TECTONIC_CACHE_DIR` (a persistent volume)
  so repeated compiles reuse downloaded packages.

The runner enforces the timeout itself: on expiry it terminates the process
(SIGTERM, then SIGKILL after a short grace) and returns `timed_out=True`. It
checks the `CancelToken` cooperatively; if cancelled it kills the process and
returns `cancelled=True`.

#### 5.2.4 Cancellation (`limits.py` or `runner.py`)

Provide a lightweight `CancelToken` (wraps `asyncio.Event`): `.cancel()`,
`.is_cancelled` / `await .wait()`. Spec 22 uses it to implement job
cancellation; here it just needs to be honoured.

#### 5.2.5 Resource limits (`limits.py`)

```python
@dataclass(slots=True, frozen=True)
class ResourceLimits:
    max_input_files: int        # reject assembly beyond this count
    max_input_bytes: int        # total assembled input size cap
    max_output_bytes: int       # cap captured output / artifact total
    max_log_bytes: int          # truncate .log capture beyond this
    max_stdout_bytes: int       # truncate stdout/stderr capture
    cpu_seconds: int | None     # POSIX RLIMIT_CPU on the child (best-effort)
    address_space_bytes: int | None  # RLIMIT_AS on the child (best-effort)
```

Defaults come from settings (§5.5). On POSIX, the real runner applies CPU/AS
rlimits via the subprocess `preexec_fn` (documented as best-effort; not a
substitute for container limits). The service validates input counts/sizes
*before* spawning and returns `SYSTEM_ERROR` with a clear message if exceeded.

#### 5.2.6 Workdir assembly (`workdir.py`)

```python
async def create_workdir(root: Path, compile_id: UUID) -> Path: ...
    # makes <root>/<compile_id>/ with input/ and output/ subdirs, mode 0o700

async def assemble_inputs(
    *,
    workdir: Path,
    project_id: UUID,
    docs: DocumentSource,    # injected reader over spec-13 content
    files: FileSource,       # injected reader over spec-14 storage
    limits: ResourceLimits,
) -> AssembledInputs: ...     # counts, total bytes, list of written paths

def safe_join(base: Path, rel: str) -> Path: ...
    # rejects absolute paths, '..' traversal, symlinks; raises UnsafePathError

async def cleanup_workdir(workdir: Path) -> None: ...  # rm -rf, never raises
```

- `DocumentSource` and `FileSource` are thin **Protocols** the service depends
  on, with concrete adapters that read from specs 13 and 14. This keeps the
  compile module decoupled and makes them trivially fakeable in tests.
- Every written path goes through `safe_join`. Paths that escape the workdir,
  are absolute, or contain `..` segments cause the whole compile to fail with
  `SYSTEM_ERROR` (defensive; the file-tree spec should already prevent these).
- Assembly is bounded by `limits.max_input_files` / `max_input_bytes`.
- The `output/` directory is created empty; Tectonic writes there.

#### 5.2.7 The service entry point (`service.py`)

```python
class CompileService:
    def __init__(
        self,
        *,
        settings: Settings,
        runner: TectonicRunner,
        docs: DocumentSource,
        files: FileSource,
        packages: PackageConfig,
    ) -> None: ...

    async def compile(
        self,
        opts: CompileOptions,
        cancel: CancelToken | None = None,
    ) -> CompileResult: ...
```

`compile()` algorithm:
1. Resolve effective timeout and limits from `opts`/settings.
2. `create_workdir`; on any later step always `cleanup_workdir` in a `finally`
   unless `keep_workdir` is set.
3. `assemble_inputs`; on limit violation return `SYSTEM_ERROR`.
4. Verify `main_file` exists in the assembled inputs; else `FAILURE` with a
   helpful message ("root document not found").
5. Call `runner.run(...)`.
6. Read the `.log` from `output/` (or stdout fallback), truncated to
   `max_log_bytes`. Discover artifacts in `output/` (`workdir.collect_outputs`).
7. Map the run outcome to a `CompileStatus`:
   - `timed_out` → `TIMEOUT`; `cancelled` → `CANCELLED`.
   - exit 0 **and** a PDF present → `SUCCESS`.
   - otherwise → `FAILURE` (LaTeX error: no PDF) — still return log/stdout.
8. Build and return `CompileResult`.

The service must be **import-light and side-effect free at import time** (no
subprocess at module load). It is constructed via the app's DI container so spec
22 can reuse the same instance.

### 5.3 Frontend / UI

None. (PDF preview is spec 24.)

### 5.4 Real-time / jobs / external integrations

- **External binary:** `tectonic`. Installed in the backend image (Alpine,
  multi-stage). The Dockerfile must install a pinned Tectonic version and
  pre-create/point `TECTONIC_CACHE_DIR` at a volume. Document the install in the
  ADR; the actual Dockerfile change may be staged here and finalised in the
  Docker spec (56).
- No ARQ here (spec 22). No WebSocket. No LLM.

### 5.5 Configuration

#### New env vars (add to `.env.example`)

| Var | Default | Meaning |
| --- | --- | --- |
| `TECTONIC_BIN` | `tectonic` | Path/name of the Tectonic executable. |
| `TECTONIC_CACHE_DIR` | `/var/cache/tectonic` | Persistent package cache dir. |
| `TECTONIC_BUNDLE_URL` | _(empty)_ | Optional pinned bundle URL/path; empty = Tectonic default bundle. |
| `TECTONIC_OFFLINE` | `false` | If `true`, forbid network fetches (only cached/bundled packages). |
| `COMPILE_WORKDIR_ROOT` | `/tmp/inkstave-compiles` | Root under which per-compile workdirs are created. |
| `TECTONIC_COMPILE_TIMEOUT_S` | `60` | Default wall-clock timeout per compile. |
| `COMPILE_MAX_INPUT_FILES` | `2000` | Assembly file-count cap. |
| `COMPILE_MAX_INPUT_BYTES` | `104857600` (100 MiB) | Assembly total-size cap. |
| `COMPILE_MAX_OUTPUT_BYTES` | `104857600` (100 MiB) | Output total-size cap. |
| `COMPILE_MAX_LOG_BYTES` | `2097152` (2 MiB) | Captured `.log` truncation cap. |
| `COMPILE_MAX_STDOUT_BYTES` | `262144` (256 KiB) | stdout/stderr capture cap. |
| `COMPILE_CPU_SECONDS` | `60` | Best-effort `RLIMIT_CPU` on child (empty disables). |
| `COMPILE_ADDRESS_SPACE_BYTES` | `2147483648` (2 GiB) | Best-effort `RLIMIT_AS` (empty disables). |
| `COMPILE_KEEP_WORKDIR_ON_FAILURE` | `false` | Keep failed workdirs for debugging. |

All are read through the Pydantic `Settings` object from spec 02 (no `os.environ`
reads scattered in code).

#### The editable package config — `infra/tectonic/packages.toml`

This single file is the documented place to control the LaTeX package set without
touching application code. It is **declarative configuration consumed by
`packages.py`**, not executable code.

```toml
# infra/tectonic/packages.toml
#
# Inkstave LaTeX package configuration for the Tectonic engine.
#
# Tectonic fetches the LaTeX packages a document needs on demand from a
# "bundle" and caches them in TECTONIC_CACHE_DIR. You normally do NOT list every
# package by hand — Tectonic resolves dependencies automatically. This file lets
# a deployer: (a) pin the bundle, (b) declare a lightweight default set to
# pre-warm the cache so first compiles are fast and work offline, and
# (c) add extra packages without editing any source code.

[bundle]
# Empty url => use Tectonic's built-in default bundle for the pinned format.
# Pin this in production for reproducible builds.
url = ""                 # overrides TECTONIC_BUNDLE_URL when non-empty
format = "latex"         # tectonic output format / TeX format

[cache]
# Where downloaded packages live. Empty => use TECTONIC_CACHE_DIR env var.
dir = ""
# If true, a build step pre-fetches the `prewarm` set into the cache so the
# image ships with them and offline compiles work.
prewarm_on_build = true

[packages]
# The lightweight default set pre-warmed into the cache. These are the packages
# a typical document uses; extend this list to make more packages available
# offline. Adding here does NOT require code changes — only re-running the
# prewarm/build step.
prewarm = [
  "amsmath",
  "amsfonts",
  "amssymb",
  "geometry",
  "graphicx",
  "hyperref",
  "babel",
  "inputenc",
  "fontenc",
  "xcolor",
  "booktabs",
  "caption",
  "enumitem",
  "listings",
]

[policy]
# When true, compiles may reach the network to fetch packages not yet cached.
# When false (recommended for hardened/offline deployments), only prewarmed and
# previously-cached packages are available; a missing package fails the compile.
allow_network_fetch = true
```

`packages.py` loads this file into a `PackageConfig` dataclass with sensible
fallbacks to env vars, validates types, and exposes:
- `bundle_url() -> str | None`
- `cache_dir() -> Path`
- `prewarm_packages() -> list[str]`
- `allow_network_fetch() -> bool`

A small `prewarm` routine (callable from a build step / CLI, not from the request
path) iterates `prewarm` packages and triggers Tectonic to cache them. It is
out of the request hot path and is itself stubbed in tests.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the *orchestration* approach only.
> Overleaf's CLSI runs **latexmk over a TeX Live install inside Docker
> containers** — a fundamentally different engine model from Inkstave's single
> Tectonic binary. Take the structure (assemble → run → discover outputs → clean
> up → lock), not the commands.

- `services/clsi/app/js/CompileManager.js` — top-level orchestration: how a
  compile is sequenced (write resources, run, find outputs, handle errors,
  timeout/cleanup). Note `doCompileWithLock` and the timeout handling. Inkstave
  collapses this into `CompileService.compile`.
- `services/clsi/app/js/LatexRunner.js` — how the engine process is spawned with
  a timeout and a process table for kill/cancel; the `timeout` default and
  SIGTERM/SIGKILL idea. Inkstave's `LocalTectonicRunner` reimplements this with
  `asyncio` subprocesses and a `CancelToken`.
- `services/clsi/app/js/ResourceWriter.js` — materialising project resources to a
  directory before compiling, and path handling. Inkstave's `workdir.py` does
  the equivalent with strict `safe_join` (Inkstave reads inputs from specs 13/14
  rather than downloading from URLs).
- `services/clsi/app/js/OutputFileFinder.js` — discovering output files by
  walking the compile dir and excluding inputs. Inkstave avoids the input/output
  diff by writing outputs to a dedicated `output/` dir, but the walk-and-classify
  idea informs `collect_outputs`.
- `services/clsi/app/js/CommandRunner.js` / `LocalCommandRunner.js` — the
  runner-abstraction indirection (local vs. docker) that motivates Inkstave's
  injectable `TectonicRunner` Protocol.
- `services/clsi/app/js/LockManager.js` — per-project compile locking and
  concurrency caps; concept only (Inkstave's locking/concurrency lives in spec
  22's queue, but the lock-timeout-vs-compile-timeout relationship is useful).

## 7. Acceptance criteria

Given/When/Then, each independently verifiable (with the runner stubbed unless
stated otherwise):

1. **Given** a project with one document `main.tex` and no binary files, **when**
   `CompileService.compile` runs with a runner stub that simulates exit 0 and
   writes `output/main.pdf`, **then** the result has `status == SUCCESS`, a
   non-null `pdf` artifact with `content_type == "application/pdf"`, and a
   populated `log_text`.
2. **Given** a runner stub that simulates a LaTeX error (exit ≠ 0, no PDF),
   **when** compile runs, **then** `status == FAILURE`, `pdf is None`, and
   `log_text`/`stderr` are still returned to the caller.
3. **Given** a runner stub that reports `timed_out=True`, **when** compile runs,
   **then** `status == TIMEOUT` and no exception escapes the service.
4. **Given** a `CancelToken` that is cancelled before/while the runner runs,
   **when** compile runs, **then** `status == CANCELLED`.
5. **Given** `keep_workdir=False` (default), **when** compile finishes in any
   outcome (success/failure/timeout/cancel/system error), **then** the workdir no
   longer exists on disk; **and** with `keep_workdir=True` it remains and
   `result.workdir` points to it.
6. **Given** project documents and binary files from specs 13/14, **when**
   inputs are assembled, **then** each file exists at its correct relative path
   under `<workdir>/input/`, and the input file count/bytes are within limits.
7. **Given** a document whose path attempts traversal (`../../etc/passwd`) or is
   absolute, **when** assembly runs, **then** `safe_join` rejects it and compile
   returns `SYSTEM_ERROR` without writing outside the workdir.
8. **Given** assembled inputs exceeding `COMPILE_MAX_INPUT_FILES` or
   `COMPILE_MAX_INPUT_BYTES`, **when** compile runs, **then** it returns
   `SYSTEM_ERROR` *before* spawning the runner (assert the runner was not
   called).
9. **Given** a runner that produces a `.log` larger than `COMPILE_MAX_LOG_BYTES`,
   **when** compile runs, **then** `log_text` is truncated to the cap and
   `truncated is True`.
10. **Given** `infra/tectonic/packages.toml`, **when** `packages.py` loads it,
    **then** `prewarm_packages()` returns the listed packages and
    `allow_network_fetch()` reflects `[policy].allow_network_fetch`; **and** when
    the file is missing, sane env-var-backed defaults are used without crashing.
11. **Given** the default config, **when** the (real) `LocalTectonicRunner`
    builds its argument vector, **then** it uses `asyncio.create_subprocess_exec`
    with a list of args (no shell), targets the configured `output/` dir, and
    points the cache at `TECTONIC_CACHE_DIR` — assert the constructed argv via a
    seam that returns it without executing.
12. **Given** an offline configuration (`TECTONIC_OFFLINE=true` /
    `allow_network_fetch=false`), **when** the runner argv is built, **then** it
    includes the offline/only-cached flag(s).

## 8. Test plan

> Real Tectonic compiles are slow and network-touching; they MUST NOT run in the
> unit or integration tiers. The runner is the seam: substitute a `FakeRunner`
> that writes predetermined files into `output/` and returns a chosen
> `RunOutcome`. Assembly and result-mapping logic are then fully testable in
> milliseconds.

- **Unit (pytest):**
  - `safe_join` accepts in-tree paths; rejects absolute, `..`, and symlinked
    escapes.
  - Workdir create → assemble (with fake `DocumentSource`/`FileSource`) → collect
    outputs → cleanup; assert files, counts, bytes, and that cleanup is total.
  - Result mapping: every `RunOutcome` shape maps to the correct
    `CompileStatus` (criteria 1–4).
  - Limit enforcement: oversized/too-many inputs short-circuit before the runner
    is called (assert via a runner mock's call count).
  - Log/stdout truncation and the `truncated` flag.
  - `packages.py`: parse the real `infra/tectonic/packages.toml`, plus a missing
    file and a malformed file (graceful fallback / clear error).
  - `LocalTectonicRunner` argv construction via a non-executing seam (criteria
    11–12). The subprocess itself is **not** spawned in this tier.
- **Integration (pytest):**
  - Drive `CompileService.compile` end-to-end with `FakeRunner` and the real
    spec-13/spec-14 adapters against a temp project, asserting workdir lifecycle,
    artifact discovery, and cleanup on both success and failure paths.
  - A `keep_workdir=True` path leaves artifacts; a default path removes them.
- **E2E (Playwright):** none in this spec (no UI). A single **tiny smoke
  compile** that actually invokes the `tectonic` binary on a one-line
  `\documentclass{article}\begin{document}hi\end{document}` may be provided as a
  **dedicated, opt-in test** (e.g. marked `@pytest.mark.smoke` / gated behind
  `RUN_REAL_COMPILE=1`) that is **excluded from the default fast suite** and from
  CI's fast tier. It exists to prove the binary + bundle/cache wiring works, runs
  at most once, and must be skippable so the 2-minute budget is never threatened.
- **Performance/budget note:** the default `pytest` run executes zero real
  compiles. The only real compile lives behind an opt-in marker. Net added time
  to the fast suite: a few milliseconds.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (`backend/app/compile/` module,
      `infra/tectonic/packages.toml`).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; default suite runs zero real compiles.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (`ruff`, `mypy`/`pyright`).
- [ ] New env vars documented in `.env.example`; `infra/tectonic/packages.toml`
      committed with the documented default set.
- [ ] ADR under `docs/` records the sandbox/security model: per-compile isolated
      0700 workdir, no-shell subprocess, best-effort rlimits, the
      input/output-dir separation, and the explicit **CE-style "trusted users"
      caveat** (single Tectonic process is not a hard security boundary on its
      own; rely on container isolation and only allow trusted collaborators to
      submit arbitrary LaTeX, which can execute shell-escape-like behaviour or
      exhaust resources — Inkstave disables shell-escape and bounds resources but
      states the residual risk).
- [ ] No Overleaf code copied.
