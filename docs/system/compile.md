# Compile

Turns a project into a PDF. A member presses the compile button, the API records a `compiles` row and
enqueues an ARQ job, the worker writes the project to a scratch directory, runs Tectonic, stores the
outputs and publishes status over Server-Sent Events. The same domain answers SyncTeX queries (source to
PDF and back) and parses the LaTeX log into problems. Specs 21 (service), 22 (queue), 23 (outputs),
25 (test tiers), 26 (SyncTeX), 27 (log parsing), 105 (sandbox and daily quota).

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/compile/__init__.py`, `backend/src/inkstave/modules/compile/deps.py`, `backend/src/inkstave/modules/compile/schemas.py` | Public names; `get_compile_enqueuer` (one ARQ pool on `app.state`); request and response schemas |
| `backend/src/inkstave/modules/compile/assembly/workdir.py`, `backend/src/inkstave/modules/compile/assembly/sources.py` | `create_workdir`, `safe_join`, `assemble_inputs`, `collect_outputs`, `cleanup_workdir`; `DbDocumentSource`, `StorageFileSource` |
| `backend/src/inkstave/modules/compile/queue/coordinator.py`, `backend/src/inkstave/modules/compile/queue/enqueuer.py` | `CompileCoordinator` (coalesce, caps, enqueue); `ArqEnqueuer` |
| `backend/src/inkstave/modules/compile/queue/jobs.py`, `backend/src/inkstave/modules/compile/queue/repository.py` | `run_compile`; `CompileRepository` |
| `backend/src/inkstave/modules/compile/queue/stream.py`, `backend/src/inkstave/modules/compile/queue/retention.py` | Redis channels, cancel flag, SSE frames; `cleanup_compile_outputs` |
| `backend/src/inkstave/modules/compile/running/service.py` | `CompileService`: assemble, resolve root, run, map the result |
| `backend/src/inkstave/modules/compile/running/runner.py`, `backend/src/inkstave/modules/compile/running/sandbox.py`, `backend/src/inkstave/modules/compile/running/stub.py` | `LocalTectonicRunner`, `ProcessWatch`; `SandboxedTectonicRunner`, `validate_main_file`; `MockTectonicRunner` |
| `backend/src/inkstave/modules/compile/running/limits.py`, `backend/src/inkstave/modules/compile/running/packages.py`, `backend/src/inkstave/modules/compile/running/result.py`, `backend/src/inkstave/modules/compile/running/errors.py` | `ResourceLimits`, `CancelToken`; `load_package_config`; result types; exceptions |
| `backend/src/inkstave/modules/compile/outputs/store.py`, `backend/src/inkstave/modules/compile/outputs/repository.py` | `OutputStore`, `classify`, `parse_range`; `OutputRepository` |
| `backend/src/inkstave/modules/compile/models/compile.py`, `backend/src/inkstave/modules/compile/models/compile_output.py` | SQLAlchemy models |
| `backend/src/inkstave/modules/compile/routes/compile.py`, `backend/src/inkstave/modules/compile/routes/helpers.py`, `backend/src/inkstave/modules/compile/routes/synctex.py`, `backend/src/inkstave/modules/compile/routes/logparse.py` | HTTP API |
| `backend/src/inkstave/modules/compile/synctex/parser.py`, `backend/src/inkstave/modules/compile/synctex/service.py`, `backend/src/inkstave/modules/compile/synctex/models.py` | SyncTeX parser, index cache, models |
| `backend/src/inkstave/modules/compile/logparse/latex_log_parser.py`, `backend/src/inkstave/modules/compile/logparse/service.py`, `backend/src/inkstave/modules/compile/logparse/models.py` | Log parser, service, models |
| `backend/src/inkstave/worker.py` | ARQ `WorkerSettings`, `_build_runner`, `_register_compile` |
| `backend/src/inkstave/compile/worker.py` | Compatibility entrypoint named by every compose file; re-exports the one above |
| `infra/tectonic/Dockerfile`, `infra/tectonic/packages.toml` | The offline `inkstave-tectonic` image; package configuration |
| `infra/tectonic/compat-rules.toml` | Rules that flag constructs of imported Overleaf templates. Read by the projects module, not by Tectonic (spec 120) |
| `frontend/src/modules/pdf-preview/` | Compile button, log, problems, PDF viewer; see the frontend file. `frontend/src/modules/pdf-preview/PdfPageText.tsx` lays the page's text over its canvas, which is what makes it selectable |
| `backend/tests/golden/`, `backend/tests/smoke/test_real_compile.py` | Parser fixtures; the one opt-in real compile |

## Data

`compiles`, created by `backend/migrations/versions/20260609_2117_af1f233e2334_create_compiles.py`. One row
per request that was not coalesced. Columns: `project_id` and `requested_by` (FK, cascade), `status`
(`queued`, `running`, `success`, `failure`, `timeout`, `cancelled`, `error`), `main_file` (the requested root,
not updated when `_resolve_root` falls back), `job_id`, `error_message`, `exit_code`, `duration_ms`, `has_pdf`,
`artifact_manifest`, `log_excerpt` (last 2000 characters), `started_at`, `finished_at`, timestamps.

`compile_outputs`, created by
`backend/migrations/versions/20260609_2138_df0daad1ac8d_create_compile_outputs.py`. One row per artifact:
`compile_id`, `project_id`, `name`, `rel_path`, `kind` (`pdf`, `log`, `synctex`, `aux`, `other`, from
`classify`), `content_type`, `size_bytes`, `storage_key`, `etag` (SHA-256 hex), `created_at`. Unique on
`(compile_id, name)`.

Disk: `<COMPILE_WORKDIR_ROOT>/<compile_id>/input` and `.../output`, mode 0700, on the worker only. Object
storage: `<COMPILE_OUTPUT_PREFIX>/<project_id>/<compile_id>/<name>`, through the documents domain's
`ObjectStore`.

Redis: `compile:events:{id}` pub/sub for status; `compile:cancel:{id}` as a flag with a TTL and as a channel.
The worker polls the flag; nothing subscribes to the channel. Rate counters are `rl:compile:user:<id>` and
`rl:compile_daily:user:<id>`. In process: `_CACHE` in the SyncTeX service, an LRU of parsed indexes keyed by
`(compile_id, etag)`.

## Routes

All under `/api/v1/projects/{project_id}`. Errors use the `ErrorEnvelope` body; the table gives
`error.type`. A non-member gets 404 `project_not_found` on every route, never 403.

| Method and path | What it does | Errors |
|---|---|---|
| `POST /compile` | Body `CompileRequest` (`main_file`, `force`). Flushes open CRDT rooms, then the coordinator. 202 with the status | 401 `unauthorized`, 403 `insufficient_role`, 404, 429 `rate_limited`, 429 `compile_concurrency_limit` |
| `GET /compile/latest` | Newest compile of the project | 404 `compile_not_found` |
| `GET /compile/{compile_id}` | One compile | 404 `compile_not_found` |
| `POST /compile/{compile_id}/cancel` | Sets the cancel flag. A queued row becomes `cancelled` here; a running one stays `running` until the job settles it. Terminal rows return unchanged | 404 `compile_not_found` |
| `GET /compile/{compile_id}/outputs` | `OutputSummary` list | 404 `compile_not_found` |
| `GET /compile/{compile_id}/output.pdf` | Streams the PDF. `Range` gives 206, a bad range 416, a matching `If-None-Match` 304 | 404 `compile_not_found` |
| `GET /compile/{compile_id}/output.log` | Streams the full log as text | 404 `compile_not_found` |
| `GET /compile/{compile_id}/events` | SSE status stream. Accepts the `Authorization` header or `?access_token=` (`sse_user`) | 401, 404 `project_not_found`, 404 `compile_not_found` |
| `GET /compiles/{compile_id}/problems` | Parsed log. `compile_id` may be `latest` | 404 `log_unavailable` |
| `GET /synctex/code-to-pdf` | Query `file`, `line`, `column?`, `compile_id?` | 404 `synctex_unavailable`, 404 `synctex_no_match`, 422 `validation_error` |
| `GET /synctex/pdf-to-code` | Query `page`, `h`, `v`, `compile_id?` | same |

The compile routes require `Capability.COMPILE`; SyncTeX and problems require `Capability.PROJECT_READ`.
`compile_allowed_for_viewers` removes `COMPILE` from viewers, which then get 403. The SSE route authorizes
inline with `role_for`, so any member may read events regardless of that setting.

## How it works

**Request.** `enqueue_compile` runs the two rate-limit dependencies, then `flush_open_project_docs` so the
worker sees current text and not the debounced `documents.content`. `CompileCoordinator.request_compile`:

1. Unless `force` is set or `compile_debounce_coalesce` is off, returns the project's active compile if any.
2. Counts queued plus running rows for the project and the user. Over either cap raises
   `CompileConcurrencyError` (429, `Retry-After: 5`).
3. Inserts the row, calls `ArqEnqueuer.enqueue`, stores `job_id`. The session commits when the route ends.

The frontend calls `requestCompile(projectId)` with no options, so it always sends `main_file: null` (the
backend then uses `main.tex`) and never `force`. `useCompile` ignores clicks while a compile is active.

**Job.** `run_compile` binds logging context and records metrics, then `_compile_once`:

1. Loads the row. A missing row returns a summary with `status: error` and writes nothing.
2. `_settle_if_cancelled`: a terminal row is returned as is; a set flag settles the row `cancelled`.
3. `_settle_if_unauthorized`: rechecks `Capability.COMPILE`. A requester who lost access gets `error`.
4. Sets `running`, commits, publishes.
5. `_compile_with_cancel` starts `_cancel_watcher`, which polls the flag every 50 ms and trips the
   `CancelToken`, and calls `CompileService.compile` with `keep_workdir=True`.
6. `_persist_outputs` copies artifacts through `persist_hook` and removes the workdir.
7. `_outcome_fields` builds the terminal fields; `job.finish` commits and publishes.

An exception from the service settles `error`; so does a persistence failure, with `output persistence
failed: ...`. `_run_compile_body` removes the workdir in a `finally` as a backstop. `_STATUS_MAP` maps
`system_error` to `error`. The metric labels only `success`, `failure` and `timeout`; the rest count as
`failure`.

**Service.** `CompileService._run`:

1. Returns `cancelled` if the token is already tripped.
2. `assemble_inputs` writes documents, then binary files, under `input/`. Paths come from `get_tree`, so
   `tree_max_nodes` also caps them. `_Budget` raises `InputLimitError`; `safe_join` raises `UnsafePathError`
   on absolute paths, `..` and symlink escapes. Both become `system_error`.
3. `_resolve_root` keeps `main_file` if it exists. Otherwise it takes the shallowest `.tex` containing
   `\documentclass`, or the first `.tex` by depth then path. No `.tex` at all is `failure`.
4. `on_assembled` commits the session, so no transaction stays open while Tectonic runs.
5. The runner runs. `_build_result` collects outputs, reads `<stem>.log` (or stdout) up to
   `compile_max_log_bytes`, and sets the status: cancelled, then timed out, then `success` if exit code 0 and a
   PDF exists, otherwise `failure`.

A catch-all in `compile` turns any other exception, including a `validate_main_file` rejection or a missing
`docker` binary, into `system_error`. The job stores the first 1000 characters in `error_message`.

**Runners.** `_build_runner` in `backend/src/inkstave/worker.py` picks one per worker. Local and sandbox share
the Tectonic argv: `-X compile <main> --outdir <dir> --outfmt pdf --synctex --keep-logs --keep-intermediates`,
plus `--only-cached` when offline and `--bundle` when set.

| Runner | Selected by | Isolation |
|---|---|---|
| `LocalTectonicRunner` | default | No shell, `cwd` at `input/`, env limited to `PATH`, `HOME`, `LANG`, `LC_ALL`, `TMPDIR`, `TECTONIC_CACHE_DIR`, `RLIMIT_CPU` and `RLIMIT_AS`. No filesystem or network isolation |
| `SandboxedTectonicRunner` | `COMPILE_RUNNER=sandbox` | `docker run --rm` per compile, offline |
| `MockTectonicRunner` | `COMPILE_MODE=mock` | No subprocess. `% INKSTAVE_E2E_COMPILE_ERROR` or `\inkstaveforceerror` in the main file gives an error log, exit 1, no PDF |

`ProcessWatch` races the process against the token and the wall-clock timeout. On either, the local runner
sends SIGTERM and after 2 s SIGKILL; the sandbox runner runs `docker kill <name>` first.

**Sandbox.** `build_command` produces: `--runtime=runsc --network none --read-only --tmpfs /tmp:size=<n>m
--user 65534 --cap-drop ALL --security-opt no-new-privileges --pids-limit --memory --cpus
--name inkstave-compile-<hex> --workdir /work -v <workdir>/input:/work:ro -v <output_dir>:/out`, then the image
and the Tectonic argv. `validate_main_file` allows only `/`-separated segments that start alphanumeric and
contain `[A-Za-z0-9._+-]`. As shipped this mode does not work, see Points of attention.
`infra/tectonic/Dockerfile` warms the Tectonic cache in a build stage from a hand-written package list, copies
only the cache into an Alpine runtime stage, and sets `USER 65534:65534`. It has no entrypoint because the
runner passes the whole argv.

**Outputs.** `OutputStore.persist` reads each artifact into memory, hashes it, writes it to storage and upserts
its row, before the terminal event. Artifacts are stored for every run, including failures and cancels.

**Retention.** `cleanup_compile_outputs` is an ARQ cron; `_sweep_minutes` turns `COMPILE_RETENTION_SWEEP_S` into
cron minutes. `list_compiles_for_retention` selects compiles with outputs that fall past
`compile_retain_per_project` or are older than `compile_retention_max_age_s`, up to `compile_retention_batch`.
`delete_for_compile` deletes storage objects before rows; the `compiles` row stays. `delete_project` in
`backend/src/inkstave/modules/projects/routes/projects.py` calls `delete_for_project`, because a soft delete
does not cascade.

**SSE.** `sse_stream` reads the snapshot, subscribes, then emits `event: status` frames shaped like
`CompileStatusResponse`, plus a `: keep-alive` comment every `compile_sse_keepalive_s`. It closes on a terminal
status.

**SyncTeX.** `SyncTexIndex` parses the gzip text directly, without the `synctex` binary. `normalise_path` turns
each `Input:` into a project path, dropping the compile folder or the sandbox's `/work`; an absolute path left
is outside the project, so it is not indexed, and `inverse` ignores its boxes. Log paths use the same function. Coordinates are PDF
points, origin top-left, y downward. `forward` returns the boxes of the first indexed line at or after the
requested one, else the last line of the file; `column` is ignored. `inverse` returns the smallest box
containing the point, else the nearest. `compile_id` defaults to the latest successful compile.

**Log parsing.** `parse_latex_log` rejoins wrapped lines, tracks a file stack from `(` and `)`, and recognises
`! ` errors with an `l.<n>` marker, `file:line: msg` errors, LaTeX, package, class and font warnings, and
overfull or underfull boxes (`info`). `LogProblemsService` keeps the tail of an oversized log, adding a
`log-truncated` problem, and past the cap appends `too-many-problems`. The counts include those rows.

**Worker wiring.** `startup` loads `infra/tectonic/packages.toml` relative to the working directory, then
`_register_compile` puts `make_compile_service`, `persist_hook` and `make_output_store` in the ARQ `ctx`.
`_register_template_import` loads `infra/tectonic/compat-rules.toml` (a bad rule stops the worker) and
sets `start_template_compile`. The import job calls it after an Overleaf template import: it builds a
`CompileCoordinator` as the requester, over an ARQ pool that `startup` creates and `shutdown` closes.
`WorkerSettings` registers `run_compile` with `max_tries=1` and `timeout=compile_job_timeout_s`. The worker
serves one queue, shared with agent, e-mail, history, notification and import jobs. `max_jobs` is not set, so
ARQ's default of 10 applies across all of them.

## Testing

There is no testkit package. `backend/tests/unit/test_testkit.py` checks the stubs of spec 54, among them
`MockTectonicRunner`. Doubles live beside the tests: `FakeRunner` and `build_service` in
`backend/tests/unit/test_compile_service.py`, `StubService`, `CancelAwareWorkdirService` and `_ctx` in
`backend/tests/integration/_compile_job_support.py`, `_StubService` in
`backend/tests/integration/_compile_outputs_support.py`, `FakeEnqueuer` in
`backend/tests/integration/test_compile_api.py`. `_no_real_compile` in `backend/tests/fixtures/env.py` is
autouse and replaces `LocalTectonicRunner.run` with a failure unless `RUN_REAL_COMPILE=1`.

`backend/tests/golden/` runs in the default suite. `backend/tests/golden/logparse_fixtures.py` holds a sample
log and `backend/tests/golden/synctex_fixtures.py` hand-written SyncTeX files with round coordinates. Neither
was captured from a Tectonic run.

`backend/tests/smoke/test_real_compile.py` is skipped unless `RUN_REAL_COMPILE=1` and `tectonic` is on `PATH`.
No CI job or make target sets that variable. It covers the local runner only; no test runs a container.
Playwright runs with `COMPILE_MODE=mock`, set in `frontend/playwright.config.ts`.

## Rules and guarantees

| Invariant | Test |
|---|---|
| A non-forced request while a compile is active returns that compile | `backend/tests/integration/test_compile_coordinator.py::test_coalesce_returns_inflight` |
| Queued plus running compiles are capped per project and per user | `backend/tests/integration/test_compile_coordinator.py::test_project_concurrency_cap_raises`, `backend/tests/integration/test_compile_coordinator.py::test_user_concurrency_cap_raises` |
| The route carries both rate policies; the 31st in the daily window is refused | `backend/tests/unit/test_compile_daily_quota.py::test_compile_route_attaches_the_daily_quota_dependency`, `backend/tests/unit/test_compile_daily_quota.py::test_thirty_first_compile_in_the_window_is_blocked` |
| The job timeout must exceed the engine timeout | `backend/tests/integration/test_compile_coordinator.py::test_job_timeout_must_exceed_engine_timeout` |
| `run_compile` never retries | `backend/tests/integration/test_compile_job.py::test_run_compile_job_does_not_auto_retry` |
| A compile cancelled before pickup does not compile or persist | `backend/tests/integration/test_compile_job_cancel.py::test_precancelled_exits_without_compiling` |
| A cancel during the run ends `cancelled` and removes the workdir | `backend/tests/integration/test_compile_job_cancel.py::test_cancel_during_run_trips_token` |
| Cancelling a queued compile is immediate and idempotent | `backend/tests/integration/test_compile_api.py::test_cancel_queued_compile` |
| Timeout and cancel kill the sandbox container by name | `backend/tests/unit/test_compile_sandbox_runner.py::test_timeout_kills_the_container`, `backend/tests/unit/test_compile_sandbox_runner.py::test_cancel_kills_the_container_by_name` |
| Outputs are persisted before the terminal event | `backend/tests/integration/test_compile_outputs_jobs.py::test_job_persists_before_terminal_status_event` |
| No workdir survives a service exception or a persistence failure | `backend/tests/integration/test_compile_job_workdir.py::test_workdir_removed_when_service_raises`, `backend/tests/integration/test_compile_job_workdir.py::test_workdir_removed_on_persistence_failure` |
| No transaction stays open while Tectonic runs | `backend/tests/unit/test_external_timeouts.py::test_the_compile_ends_its_transaction_before_tectonic_runs` |
| Assembly rejects absolute paths, `..` and symlink escapes | `backend/tests/unit/test_compile_workdir.py::test_safe_join_rejects_unsafe`, `backend/tests/unit/test_compile_workdir.py::test_safe_join_rejects_symlink_escape` |
| Assembly enforces the file and byte caps before running | `backend/tests/unit/test_compile_workdir.py::test_assemble_enforces_file_count`, `backend/tests/unit/test_compile_workdir.py::test_assemble_enforces_byte_cap`, `backend/tests/unit/test_compile_service.py::test_input_limit_short_circuits_before_runner` |
| The local compile env holds no application secrets | `backend/tests/unit/test_compile_runner.py::test_compile_sandbox_no_shell_escape_no_inherited_secrets` |
| The docker argv carries the isolation flags; input is read-only | `backend/tests/unit/test_compile_sandbox_runner.py::test_docker_argv_carries_the_isolation_flags`, `backend/tests/unit/test_compile_sandbox_runner.py::test_mounts_are_read_only_input_and_writable_output` |
| The docker launcher env is at most `PATH` and `HOME` | `backend/tests/unit/test_compile_sandbox_runner.py::test_no_secrets_or_extra_user_data_in_argv_or_env` |
| A dangerous `main_file` never reaches the docker argv | `backend/tests/unit/test_compile_sandbox_runner.py::test_dangerous_main_files_are_rejected` |
| Retention selects past the keep window, or by age regardless of it | `backend/tests/integration/test_compile_outputs_retention.py::test_retention_selects_beyond_keep_window`, `backend/tests/integration/test_compile_outputs_retention.py::test_retention_selects_by_age` |
| Range, 304 and 416 on the PDF | `backend/tests/integration/test_compile_output_api.py::test_pdf_range_206`, `backend/tests/integration/test_compile_output_api.py::test_pdf_conditional_304`, `backend/tests/integration/test_compile_output_api.py::test_pdf_unsatisfiable_416` |
| SSE sends snapshot, then transitions, then closes on terminal | `backend/tests/integration/test_compile_api.py::test_sse_stream_emits_snapshot_then_transitions` |
| The real runner cannot run in a fast tier | `backend/tests/unit/test_compile_speed_guard.py::test_real_runner_is_blocked_in_fast_tier` |
| Log parser order, rules and file attribution on a full log | `backend/tests/golden/test_logparse_sample.py::test_sample_log_counts_and_order` |
| SyncTeX forward then inverse is stable | `backend/tests/golden/test_synctex_parser.py::test_forward_inverse_round_trip_is_stable` |
| The job rechecks access; enqueue flushes CRDT rooms; `_sweep_minutes` | no dedicated test |

## Settings

Defined in `backend/src/inkstave/core/config/groups.py`. Names are the upper case of the attribute.

| Variable | Default | Meaning |
|---|---|---|
| `COMPILE_MODE`, `COMPILE_RUNNER` | `real`, `local` | `mock` selects the stub and wins; `sandbox` selects containers |
| `COMPILE_SANDBOX_DOCKER_BIN`, `_IMAGE`, `_RUNTIME` | `docker`, `inkstave-tectonic`, `runsc` | Client, image, `--runtime` |
| `COMPILE_SANDBOX_MEMORY_MB`, `_CPUS`, `_PIDS_LIMIT`, `_TMPFS_MB` | `2048`, `1.0`, `256`, `256` | Container caps. Memory applies only when `COMPILE_ADDRESS_SPACE_BYTES` is unset |
| `TECTONIC_BIN`, `TECTONIC_CACHE_DIR` | `tectonic`, `/var/cache/tectonic` | Local runner |
| `TECTONIC_BUNDLE_URL`, `TECTONIC_OFFLINE` | empty, `false` | `--bundle` and `--only-cached`, local runner |
| `TECTONIC_COMPILE_TIMEOUT_S`, `COMPILE_JOB_TIMEOUT_S` | `60`, `120` | Wall clock; ARQ timeout. `backend/src/inkstave/core/config/settings.py` requires the second to be larger |
| `COMPILE_WORKDIR_ROOT` | `/tmp/inkstave-compiles` | Scratch root |
| `COMPILE_MAX_INPUT_FILES`, `COMPILE_MAX_INPUT_BYTES` | `2000`, `104857600` | Assembly caps |
| `COMPILE_MAX_OUTPUT_BYTES` | `104857600` | Not enforced |
| `COMPILE_MAX_LOG_BYTES`, `COMPILE_MAX_STDOUT_BYTES` | `2097152`, `262144` | Text kept in the result |
| `COMPILE_CPU_SECONDS`, `COMPILE_ADDRESS_SPACE_BYTES` | `60`, `2147483648` | Local rlimits; the second is also the sandbox `--memory`. Empty disables |
| `COMPILE_KEEP_WORKDIR_ON_FAILURE` | `false` | Honoured by the service, undone by the job |
| `COMPILE_OUTPUT_PREFIX`, `COMPILE_PDF_CACHE_MAX_AGE_S` | `compiles`, `60` | Storage prefix; `Cache-Control` max-age |
| `COMPILE_RETAIN_PER_PROJECT`, `COMPILE_RETENTION_MAX_AGE_S` | `10`, `2592000` | Keep window, 30 days |
| `COMPILE_RETENTION_SWEEP_S`, `COMPILE_RETENTION_BATCH` | `3600`, `200` | Cron interval; compiles per sweep |
| `COMPILE_MAX_CONCURRENT_PER_PROJECT`, `_PER_USER` | `1`, `3` | Active compiles |
| `COMPILE_DEBOUNCE_COALESCE` | `true` | Return the active compile |
| `COMPILE_QUEUE_NAME` | `compiles` | ARQ queue, shared with all jobs |
| `COMPILE_SSE_KEEPALIVE_S`, `COMPILE_CANCEL_FLAG_TTL_S` | `15`, `300` | Keep-alive; cancel flag TTL |
| `COMPILE_ALLOWED_FOR_VIEWERS` | `true` | Viewers hold `COMPILE` |
| `RATE_LIMIT_COMPILE`, `RATE_LIMIT_COMPILE_DAILY` | `20/60`, `30/86400` | Per user, fixed window |
| `SYNCTEX_MAX_GZ_BYTES`, `SYNCTEX_INDEX_CACHE_SIZE` | `33554432`, `16` | Size refusal; 0 disables the cache |
| `LOGPARSE_MAX_LOG_BYTES`, `LOGPARSE_WRAP_WIDTH`, `LOGPARSE_MAX_PROBLEMS` | `8388608`, `79`, `1000` | Tail kept; de-wrap width; cap |

## Points of attention

**Sandbox mode does not work as shipped.** The unit tests only assert the argv; nothing launches a
container. Four separate problems stand between the docs and a working compile, and `infra/README.md`
describes a deployment that hits all of them:

- The backend image has no `docker` client: `backend/Dockerfile` installs only `ca-certificates`,
  `fontconfig`, `ttf-freefont` and `tectonic`. Each compile ends `error`.
- `DOCKER_HOST` never reaches the client. `build_command` and `_kill_container` pass only `PATH` and `HOME`,
  so the socket-proxy setup in `infra/README.md` is ignored.
- The bind mounts use the worker's own paths. With the daemon on the host, `-v
  /tmp/inkstave-compiles/<id>/input:/work:ro` names a host path that does not exist, and docker creates it
  empty. The compile sees no input. The comment on `mkdir` in `run` assumes a shared filesystem, and the
  backend image asks for the root to stay container-local.
- The user cannot read the mounts. `create_workdir` sets 0700 on the root, workdir, `input` and `output`,
  owned by the worker (uid 10001 in the image), and the container runs as 65534. Reading `/work` and writing
  `/out` both fail, even for a worker running directly on the host.

No compose file sets `COMPILE_RUNNER`, so the default deployment stays on `local`. The flags themselves are
right: `--network none`, `--read-only`, `--cap-drop ALL` and `no-new-privileges`
are all in `_sandbox_flags`.

**Other sandbox limits.**
- `/out` is a writable bind mount with no size cap, so a compile can fill the worker's disk until the
  timeout. `COMPILE_MAX_OUTPUT_BYTES` does not help, see below.
- `COMPILE_ADDRESS_SPACE_BYTES` has a default, so `COMPILE_SANDBOX_MEMORY_MB` is ignored unless that is
  emptied. `COMPILE_CPU_SECONDS` has no effect on a container.
- `validate_main_file` rejects spaces and non-ASCII, so `café.tex` is an `error` in sandbox mode and
  fine in local mode.
- A container has no deadline of its own. If the worker dies, nothing kills it.

**Stuck compiles block a project, and nothing clears them.** There is no reaper. A row that never reaches a
terminal status holds the per-project cap, and coalescing hands that row back on every request. `force` then
gets 429 under the default cap of 1. Three ways to get there:
- The job is enqueued before the API commits. A worker that picks it up first finds no row and returns; the
  row then commits as `queued` and stays there.
- A worker crash leaves `running`, and `max_tries=1` means no retry.
- The ARQ timeout cancels the job, which skips `_outcome_fields`. The cleanup `finally` runs, the row does
  not change. The Tectonic process is not killed by that path.

An SSE client on such a row never gets a terminal event. `cancel` clears a stuck `queued` row. A stuck
`running` row has no way out through the API: the flag it sets has no worker to read it.

**The caps are checked, not locked.** `request_compile` counts and then inserts without a lock or unique
index, so simultaneous requests can pass both the coalesce and the caps.

**The daily quota counts requests.** Dependencies run first, so coalesced requests, cancelled compiles and
concurrency 429s all spend it. It is a fixed window from the first hit, not 24 rolling hours. It applies with
either runner, and it fails open when Redis is down. `RATE_LIMIT_ENABLED=false` removes it.

**Settings and config that do nothing.**
- `COMPILE_MAX_OUTPUT_BYTES` is copied into `ResourceLimits` and never read. The README's "output cap" for
  local mode and the security checklist's size limit are not true of the code.
- From `infra/tectonic/packages.toml`, only `[bundle] format` reaches a runner, and it is stored in
  `_format` and not used; `--outfmt pdf` is hard-coded. `allow_network_fetch`, `[bundle] url`, `[cache] dir`
  and `prewarm` are parsed and tested, then ignored. `--only-cached` follows `TECTONIC_OFFLINE`. The
  instructions in that file to set `allow_network_fetch = false` have no effect.
- `build_prewarm_document` has no caller. The package list in `infra/tectonic/Dockerfile` is maintained by
  hand. `backend/Dockerfile` warms only a trivial document.
- `COMPILE_KEEP_WORKDIR_ON_FAILURE` is undone by the job's cleanup, and the job is the only caller.

**`main_file` is validated only in the sandbox.** `CompileRequest` accepts any string, and `_resolve_root`
uses `input_dir / main_file`. An absolute path such as `/etc/passwd` passes `is_file()`, so the local runner
hands it to Tectonic. Local mode already trusts its users, since `\input` can read the same files, but the
API does not reject it.

**Viewer setting gaps.** With `COMPILE_ALLOWED_FOR_VIEWERS=false`, the job's recheck calls `capabilities_for`
with its default of `True`, so it does not apply the setting. The route does.

**A fallback root misleads log parsing.** `_resolve_root` does not update `row.main_file`, so
`parse_latex_log` seeds the wrong root file when the fallback fired, and unattributed problems name a file
that does not exist. The frontend always sends `main.tex`, so any project with another root takes this path.

**Retention counts every compile.** Failed and cancelled compiles fill the keep window, so ten failures
remove the last good PDF. Age wins over the window, so an idle project loses its newest outputs after 30 days.

**Small things.**
- `has_pdf` is true only on `success`, but `output.pdf` serves any stored PDF row, so a failed compile that
  left a PDF would return it.
- `problems_for` and `load_index` load the whole object into memory. `SYNCTEX_MAX_GZ_BYTES` bounds the
  compressed size only; `gzip.decompress` has no output limit.
- `infra/README.md` cites `compile/runner.py` for the sandbox runner. It lives in
  `backend/src/inkstave/modules/compile/running/sandbox.py`.
