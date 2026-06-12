# Spec 62 — Runtime Config Validation (requirements)

## 1. Summary

This spec makes misconfiguration fail fast with a readable message instead of a
deep Pydantic stack trace, removes the two confirmed duplicate keys in
`.env.example` so it parses cleanly and boots a dev instance, and adds a
`just doctor` recipe (backed by a small CLI subcommand) that reports missing or
malformed env vars plus whether Postgres and Redis are reachable. The existing
production guards in `config.py` stay; this spec adds a friendly presentation
layer and a developer-facing diagnostic on top.

## 2. Context & dependencies

- **Depends on:** spec 02 (`Settings` Pydantic-settings model and `get_settings`),
  spec 57 (the `argparse` CLI in `backend/src/inkstave/cli.py` with `migrate`,
  `check-config`, `bootstrap-admin`, `seed`, and `bootstrap/config_check.py`).
- **Unlocks:** spec 63 (seed/setup) and a smoother first-run for anyone actually
  running the app.
- **Affected areas:** backend (`config.py` validation surface, `cli.py`,
  `bootstrap/config_check.py`), infra (`.env.example`), tooling (`justfile`),
  tests (pytest).

## 3. Goals

- Starting the app (or running `check-config`/`doctor`) with a **missing or
  malformed required var** produces a single, readable, multi-line error that
  **lists every offending var by name** and what is wrong — not a raw
  `pydantic.ValidationError` traceback.
- `.env.example` has exactly **one** canonical definition of `CORS_ORIGINS` and
  **one** of `MAX_UPLOAD_BYTES` (the confirmed duplicates are removed), and the
  file parses with **no duplicate keys**.
- A `just doctor` recipe runs a `python -m inkstave.cli doctor` (new subcommand)
  that prints: (a) config validity (reusing the friendly validator), and (b)
  Postgres + Redis reachability, exiting non-zero if any check fails.
- Required vars are explicitly: `JWT_SECRET` (`jwt_secret`), `DATABASE_URL`
  (`database_url`), `REDIS_URL` (`redis_url`).

## 4. Non-goals (explicitly out of scope)

- No change to the meaning of the existing production guards
  (`_guard_production_secret`, `_guard_production_cors`,
  `_guard_production_required`, etc.) — they remain authoritative; we only
  present their failures (and missing-required failures) readably.
- No new config fields beyond what's needed; no schema migration.
- No real Postgres/Redis server requirement in the fast test tier — reachability
  is checked through injectable/mocked probes.
- No secret-management/rotation features (out of scope for runtime safety).

## 5. Detailed requirements

### 5.1 Data model (if any)

None.

### 5.2 Backend / API (if any)

Current state to build on:

- `Settings` (`pydantic_settings.BaseSettings`) lives in
  `/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/config.py`.
  `jwt_secret: str` is the only field with **no default** (strictly required);
  `database_url: str | None = None` and `redis_url: str = "redis://localhost:6379/0"`
  have defaults. Production model-validators already raise `ValueError` for weak
  JWT secret, wildcard/empty CORS, and missing `database_url`.
- `get_settings()` is `@lru_cache`-d and is first called in `create_app()`
  (`backend/src/inkstave/app.py`), so a `ValidationError` at import/startup
  currently surfaces as a raw traceback.
- `validate_config()` lives in
  `/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/bootstrap/config_check.py`
  and already catches `ValidationError` and flattens it to a human-readable list;
  the `check-config` CLI subcommand (in `backend/src/inkstave/cli.py`) prints it
  and returns exit code 0/1.

Requirements:

1. **Fail-fast required-var validation with a friendly message.** Ensure that the
   three runtime-required vars — `JWT_SECRET`, `DATABASE_URL`, `REDIS_URL` — are
   treated as **required for running the server in every environment** (not only
   prod), with a clear message naming each missing/malformed one. Two acceptable
   shapes; pick the simpler that fits the codebase:
   - (preferred) Extend the existing flattening in `config_check.py` /
     `validate_config()` so that a missing `JWT_SECRET` (already required) and an
     unset `DATABASE_URL`/`REDIS_URL` are each reported as a separate
     `"<VAR_NAME>: <reason>"` line, and have `create_app()`/lifespan call this
     friendly validator at startup so a misconfig prints the readable list and
     exits non-zero instead of dumping a `ValidationError`. Well-formedness checks:
     `DATABASE_URL` must start with `postgresql` (or `postgresql+asyncpg`),
     `REDIS_URL` must start with `redis://`/`rediss://`; `JWT_SECRET` must be
     non-empty.
   - (alternative) Add a dedicated `validate_required_runtime(settings)` helper
     that collects the same list. Keep it small and pure (string-in → list-out)
     for easy testing.
   The message format is implementation's choice but MUST: start with a one-line
   summary (e.g. "Configuration error: N problem(s)"), then one indented line per
   offending var beginning with the **env var name** (uppercase, e.g.
   `DATABASE_URL`), and MUST NOT contain a Python traceback.

2. **New `doctor` CLI subcommand** in
   `/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/cli.py`
   (`python -m inkstave.cli doctor`):
   - Runs the friendly config validation (reusing the helper from req. 1) and
     prints PASS/FAIL with the offending-var list on FAIL.
   - Probes **Postgres** reachability (open a connection / run `SELECT 1` against
     `database_url`, honouring `readiness_check_timeout_s`) and **Redis**
     reachability (`PING` against `redis_url`). Each probe must be a small,
     **injectable** function (so tests can pass fakes) — e.g. accept optional
     `db_check`/`redis_check` callables, defaulting to the real probes; reuse the
     existing readiness helpers if present (`check_db`, `create_redis_pool` in
     `app.py`). Print one PASS/FAIL line per dependency.
   - Returns exit code `0` only if config is valid **and** both dependencies are
     reachable; otherwise non-zero. Unreachable dependencies must be reported as
     a friendly line (host/port + reason), never a raw traceback.

### 5.3 Frontend / UI (if any)

None.

### 5.4 Real-time / jobs / external integrations (if any)

The `doctor` Postgres/Redis probes are the only integrations; they must be
injectable so the fast test tier never needs a real server.

### 5.5 Configuration

- **Fix `.env.example`** at
  `/home/inacio/Área de trabalho/code/inkstave/.env.example`:
  - `CORS_ORIGINS` is currently defined **twice** (lines ~34 and ~61). Keep one
    canonical definition (prefer the security-section one near line 61, with the
    clarifying CORS comment) and delete the other.
  - `MAX_UPLOAD_BYTES` is currently defined **twice** (lines ~66 and ~239). Keep
    one canonical definition (prefer the storage-section one near line 239) and
    delete the other.
  - After the fix, every key in `.env.example` appears exactly once.
- **`justfile`** at `/home/inacio/Área de trabalho/code/inkstave/justfile`: add a
  `doctor` recipe that runs `uv run --project backend python -m inkstave.cli
  doctor` (match the existing recipe style which uses `uv run --project backend`).

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently.

- `services/web/config/settings.defaults.js` and how Overleaf documents/validates
  required settings — learn the "required vs. optional with defaults" framing only.
- Overleaf's container entrypoint / healthcheck scripts under `services/web/`
  (e.g. the startup checks that abort on missing essential config) — learn the
  fail-fast pattern; do not copy.
- A "doctor"-style diagnostic has **no direct Overleaf equivalent**; build it
  from this spec.

## 7. Acceptance criteria

1. **Given** `JWT_SECRET` is unset (and env is otherwise sane), **when** the
   friendly validator runs, **then** it reports a problem whose line begins with
   `JWT_SECRET` and the output contains no Python traceback.
2. **Given** `DATABASE_URL` is unset or does not start with `postgresql`, **when**
   the friendly validator runs, **then** it reports a `DATABASE_URL` problem line.
3. **Given** `REDIS_URL` is unset or does not start with `redis://`/`rediss://`,
   **when** the friendly validator runs, **then** it reports a `REDIS_URL`
   problem line.
4. **Given** multiple required vars are missing at once, **when** the validator
   runs, **then** **all** offending vars are listed (not just the first), each on
   its own line, under a one-line summary.
5. **Given** a valid configuration, **when** the validator runs, **then** it
   reports success and (via the CLI) exits `0`.
6. **Given** `.env.example`, **when** it is parsed as key=value pairs, **then**
   there are **no duplicate keys**; specifically `CORS_ORIGINS` and
   `MAX_UPLOAD_BYTES` each appear exactly once.
7. **Given** `just doctor` (or `python -m inkstave.cli doctor`) with an injected
   **failing** Postgres probe, **when** it runs, **then** it prints a FAIL line
   for Postgres and exits non-zero, with no traceback.
8. **Given** `doctor` with injected **passing** config + Postgres + Redis probes,
   **when** it runs, **then** it prints PASS lines for all three and exits `0`.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Unit (pytest):**
  - In `backend/tests/unit/test_config_validation_62.py` (new): exercise the
    friendly validator helper directly. Use `monkeypatch.setenv`/`delenv` and
    construct `Settings(_env_file=None)` the way
    `backend/tests/unit/test_config.py` does. Assert AC1–AC5: missing
    `JWT_SECRET` / malformed `DATABASE_URL` / malformed `REDIS_URL` each produce
    the named line; multiple-missing lists all; valid config returns success;
    asserted output contains no `Traceback`.
  - In the same module (or `test_env_example_62.py`): parse
    `/home/inacio/Área de trabalho/code/inkstave/.env.example` line-by-line
    (ignore comments/blank lines, split on first `=`), collect keys, and assert
    there are no duplicates and that `CORS_ORIGINS` and `MAX_UPLOAD_BYTES` each
    appear once (AC6). Resolve the path relative to the repo root, not CWD.
  - In `backend/tests/unit/test_doctor_62.py` (new): call the `doctor` logic with
    injected fake `db_check`/`redis_check` callables. Assert exit code non-zero
    with a failing Postgres probe (AC7) and `0` with all passing (AC8), and that
    failures print a friendly line, not a traceback. Reuse the `capsys` fixture
    for stdout/stderr assertions.
- **Integration (pytest):**
  - Optional: a thin test that `create_app()` (or the lifespan path) calls the
    friendly validator and raises/exits readably when a required var is missing
    — only if it can be done without spinning real services; otherwise the unit
    coverage above suffices.
- **E2E (Playwright):** none.
- **Performance/budget note:** All checks are pure string/parse logic and
  injected probes — no real DB/Redis connection, no real server boot. Negligible
  time added.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (friendly validator, `doctor` CLI +
      `just doctor`, `.env.example` de-dup).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes (measure with `just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, `mypy`).
- [ ] `.env.example` documents every variable exactly once; `just doctor` works
      against a live dev stack (manual sanity check) and is mockable in tests.
- [ ] No Overleaf code copied.
