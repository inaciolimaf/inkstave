# Refactor 25 — Compilation (specs 21–24)

An inward quality pass over the compilation subsystem: the Tectonic service (21),
the async compile API + ARQ jobs (22), output storage & retention (23), and the
PDF-preview UI (24). **No features, no endpoints, no behaviour change** — the
production edits are leak/correctness hardening; everything else is regression
tests and a hard test-speed guard. Special attention to the project's signature
constraint: **no real LaTeX compile may run in a fast tier**.

## Baseline (before) → After

| Suite | Before | After |
| --- | --- | --- |
| **Backend** (`pytest backend/tests`, Postgres up) | ~51 s, all green, 1 skip (gated smoke) | **51.7 s**, all green, 1 skip |
| **Frontend** (`vitest run`) | 163 tests, ~10 s | **164 tests, ~10 s** |
| **Combined** | — | **~62 s — well under the 2-minute budget** |

`ruff format` / `ruff check` / `mypy` clean (backend); ESLint / Prettier / `tsc`
clean (frontend). The new tests are all fakes/stubs — they add negligible wall
time and spawn **zero** `tectonic` subprocesses.

> **How the backend timing is measured:** the ~51.7 s figure above is the
> **xdist budget path** (`just test-timed` / `scripts/run_timed.sh`, i.e.
> `pytest -n auto`) — *not* a single-threaded run, which is several times slower.
> Since fix-pack 69 that xdist path is also the default (`just test`) and CI
> wall-clock, so this number reflects the budget the gate now enforces.

## Method

Three parallel read-only scans over `compile/**` (service, runner, workdir, jobs,
coordinator, enqueuer, stream), output storage (`outputs`, `output_repository`,
`retention`, the output endpoints + range math), and the whole test suite for
real-compile leakage and slow tests. Each finding was classified
**apply / verify / defer** by risk vs. value. The subsystem was already built
test-first and in good shape, so most findings are **verified-clean**; the
applied changes are targeted leak/robustness fixes plus the mandated speed-guard.

## Findings

| id | area | category | decision | rationale / change |
| --- | --- | --- | --- | --- |
| F-001 | `tests/conftest.py` | **test-speed (signature)** | **fixed** | Added an autouse `_no_real_compile` guard that replaces `LocalTectonicRunner.run` with a loud `RuntimeError` unless `RUN_REAL_COMPILE=1`. A fast-tier test that forgets to inject a fake now fails fast and explains itself instead of silently spawning Tectonic. Regression test: `test_compile_speed_guard.py` (AC 3–4). |
| F-002 | `compile/jobs.py` | resource leak | **fixed** | The job owns workdir cleanup (`keep_workdir=True`), but the **service-exception** path returned without removing the dir. Wrapped `run_compile`'s body in a top-level `finally` that removes `COMPILE_WORKDIR_ROOT/<id>` on **every** path (idempotent, never raises). Regression tests: `test_workdir_removed_when_service_raises`, `test_workdir_removed_on_persistence_failure` (AC 1). |
| F-003 | `compile/workdir.py` | FD leak | **fixed** | `assemble_inputs` closed the destination handle but not the **source byte stream** on an early `InputLimitError`; now `aclose()`s the stream (async generator) in `finally`. Regression tests: `test_assemble_closes_file_stream{,_on_limit_error}` (scan B/A). |
| F-004 | `compile/outputs.py` | retention robustness | **fixed** | `delete_for_compile` / `delete_for_project` deleted DB rows **before** storage; a mid-sweep storage failure orphaned bytes the next pass would never re-find. Reversed to **storage-first** (storage delete is idempotent), so a failed sweep leaves rows in place and retries cleanly. Regression test: `test_delete_for_compile_is_idempotent` (scan D). |
| F-005 | `compile/outputs.py` (range) | correctness (test) | **fixed (test)** | Range/ETag math was already correct; added the missing edge-case assertions — exact-last-byte, whole-object-explicit, and **zero-length object** range requests → `416` (AC 6). |
| F-006 | `pdf-preview/hooks` | memory leak (test) | **fixed (test)** | Added a `useCompile` unmount test asserting the `EventSource` is closed (no setState-after-unmount); `usePdfDocument` already destroys the PDF.js doc on unmount **and** on replacement (spec-24 tests) (AC 7). |
| F-007 | `config.py` timeout invariant | correctness | **verified, no change** | `TECTONIC_COMPILE_TIMEOUT_S < COMPILE_JOB_TIMEOUT_S` is already enforced by a `model_validator` and tested (`test_job_timeout_must_exceed_engine_timeout`) (AC 2). |
| F-008 | `runner.py` | timeout/cancel | **verified, no change** | The child is always reaped — SIGTERM, 2 s grace, then SIGKILL+`wait()`; cancel mid-run trips the `CancelToken` (test-guarded). No zombie path found. |
| F-009 | `coordinator.py` | concurrency TOCTOU | **deferred** | A microsecond race between the debounce/active-count checks could *in theory* admit two compiles for one project. Per-project cap is **1** plus debounce-coalesce; a correct fix needs DB-level locking / a unique guard with real change risk, and the single-worker dev topology never exercises it. Deferred to a dedicated hardening pass rather than risk the green suite for a theoretical race. |
| F-010 | output endpoints | authz / streaming | **verified, no change** | Every output endpoint enforces ownership via `Depends(owned_project)` + `_require_compile` (consistent `404`, no existence leak); `LocalObjectStore` read/range streams close their handles in `finally`. |
| F-011 | retention sweep | correctness | **verified, no change** | Batch-bounded (`LIMIT :batch`), idempotent, deletes storage **and** rows; project-delete already sweeps storage via `delete_for_project` (test-guarded). The F-004 reorder makes the whole sweep retry-safe. |
| F-012 | ADR 0021 (sandbox) | security model | **verified, accurate** | Re-read against the code: no `shell=True` (argv via `create_subprocess_exec`), shell-escape never enabled, best-effort `RLIMIT_CPU`/`RLIMIT_AS` via `preexec_fn`, `safe_join` rejects absolute/`..`/symlink escapes, trusted-users caveat still correct. No drift — no edit needed (the job-owned-cleanup nuance is documented in ADR 0023). |

## Applied edits (production)

- `compile/jobs.py` — top-level `finally` workdir-cleanup backstop (F-002).
- `compile/workdir.py` — `aclose()` the source stream in `assemble_inputs` (F-003).
- `compile/outputs.py` — storage-first deletion order (F-004).

## Applied edits (tests / tooling)

- `tests/conftest.py` — autouse `_no_real_compile` speed-guard (F-001).
- `tests/unit/test_compile_speed_guard.py` — guard trips on the real runner (new).
- `tests/integration/test_compile_job.py` — workdir removed on service-exception
  and persistence-failure paths (new).
- `tests/integration/test_compile_outputs.py` — idempotent re-delete (new).
- `tests/unit/test_compile_workdir.py` — source-stream `aclose` on success + limit error (new).
- `tests/unit/test_compile_outputs_unit.py` — range edge cases incl. zero-length 416 (new).
- `frontend/.../hooks/useCompile.test.ts` — `EventSource` closed on unmount (new).

## Deliberately skipped (with rationale)

- **Coordinator TOCTOU** (F-009) — deferred; theoretical under the cap=1 +
  debounce model, fix carries real risk. Documented above.
- **Stale-workdir startup sweep** — a reclaim job for dirs orphaned by a *crashed
  worker* is feature-adjacent; the F-002 per-job backstop covers the normal
  failure modes, so a background sweeper is not worth the new surface here.
- **Streaming-response FD on client-disconnect** — framework-level; the store
  generators close in `finally` and the impact is negligible at this scale.
- **304 `Content-Length` / multi-range** — current behaviour is RFC-7232/7233
  compliant; no change.

## No new config

No new env vars were required (the timeout invariant and all caps already exist).
