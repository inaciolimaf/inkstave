# Spec 68 — Fix-Pack: Backend & Tests (requirements)

## 1. Summary

This fix-pack resolves **22 confirmed issues** found by a two-reviewer validation
pass across specs 01, 08, 11, 14, 21, 22, 23, 25, 29, 33, 36, 39, 46, 49, 52, 57,
and 59. They cluster into: `.env.example` duplicates / misplaced vars, missing
test coverage for compile-service outcome and workdir-cleanup paths, untested ARQ
job config, a slow-client backpressure setting that is never consumed, Pydantic
`extra="forbid"` gaps on two request bodies, a missing rate-limit on the
change-password endpoint, a missing optional ARQ cleanup stub, config/var naming
mismatches, and several documentation/over-delivery notes.

**Severity breakdown (adjusted):**
- major: 1 (`#217` change-password rate limit)
- minor: 14 (`#75, #80, #84, #93, #108, #126, #143, #207, #218, #28, #127, #76, #247`, and `#22` doc-note)
- nit: 7 (`#3, #44, #158, #189, #219, #243, #94`)

> Some issues are over-delivery / forward-scope deviations (`#126`, `#22`) whose
> correct resolution is a **documented note**, not a behaviour change. Each such
> issue says so explicitly below — do not regress working behaviour to "match"
> an earlier spec when a later spec already supersedes it.

## 2. Files in scope

Edit **only** these files. They are disjoint from all other fix-packs.

```
backend/src/inkstave/agent/api/jobs.py
backend/src/inkstave/api/routes/users.py
backend/src/inkstave/collab/ws/components.py
backend/src/inkstave/collab/ws/rooms.py
backend/src/inkstave/compile/worker.py
backend/src/inkstave/config.py
backend/src/inkstave/mailer/jobs.py
backend/src/inkstave/mailer/sender.py
backend/src/inkstave/mailer/templates.py
backend/src/inkstave/notifications/invite_hook.py
backend/src/inkstave/schemas/document.py
backend/src/inkstave/schemas/project.py
backend/src/inkstave/schemas/user.py
backend/src/inkstave/services/account.py
backend/tests/integration/test_compile_job.py
backend/tests/integration/test_hardening_55.py
backend/tests/unit/                       (new unit test files may be added here)
backend/tests/unit/test_compile_service.py
.env.example                              (repo-root; the "env.example" / "infra/../.env.example" entries all resolve here)
frontend/.env.example
```

**NOTE:** The payload listed the root env file three ways (`env.example`,
`infra/../.env.example`, and the issue paths' `.env.example`). They all refer to
the single repo-root **`.env.example`**. Treat it as one file. Restrict all edits
to the paths above; if a fix appears to require another file, stop and report.

## 3. Issues to fix

### 3.1 — `#3` `.env.example` duplicate `CORS_ORIGINS` (nit · spec 01)

- **File:** `.env.example`
- **Problem:** `CORS_ORIGINS` is defined twice (around lines 34 and 61). When the
  file is sourced as a shell env file the later definition silently overrides the
  earlier; when copied to `.env` it confuses developers. Spec 01 §5.5 requires each
  variable documented once.
- **Fix:** Remove the duplicate `CORS_ORIGINS` (the earlier one, ~line 34), keeping
  a single canonical definition (prefer the one in the security-hardening block at
  ~line 61, which carries the fuller comment). Verify exactly one occurrence remains.

### 3.2 — `#44` `.env.example` duplicate `MAX_UPLOAD_BYTES` (nit · spec 14)

- **File:** `.env.example`
- **Problem:** `MAX_UPLOAD_BYTES=52428800` appears twice — ~line 66 (spec-52
  security block, comment "50 MiB") and ~line 239 (spec-14 binary-storage block,
  comment "50 MB"). Same value, inconsistent comments.
- **Fix:** Keep one canonical entry (prefer the security block at ~line 66 with the
  "50 MiB" comment) and delete the other. Ensure the surviving comment is consistent
  ("50 MiB"). Verify exactly one occurrence remains.

### 3.3 — `#158` `VITE_NOTIFICATIONS_POLL_INTERVAL_MS` missing from `frontend/.env.example` (nit · spec 39)

- **Files:** `.env.example`, `frontend/.env.example`
- **Problem:** This is a Vite/frontend variable but is documented only in the root
  `.env.example` (~line 233). `frontend/.env.example` lists the other `VITE_` vars
  but omits this one — the first place a frontend dev looks.
- **Fix:** Add `VITE_NOTIFICATIONS_POLL_INTERVAL_MS=60000` (with a short comment
  matching the root file's) to `frontend/.env.example` alongside the other `VITE_`
  vars. Leave the root entry as-is (root documents all vars).

### 3.4 — `#189` `VITE_AGENT_ENABLED` missing from `frontend/.env.example` (nit · spec 46)

- **File:** `frontend/.env.example`
- **Problem:** `VITE_AGENT_ENABLED` is documented in the root `.env.example` but
  absent from `frontend/.env.example`. Spec 46 DoD item 6 requires any new build
  flag documented in `.env.example`.
- **Fix:** Add `VITE_AGENT_ENABLED=true` to `frontend/.env.example` with the same
  comment as the root file (e.g. `# show the AI agent chat panel (spec 46; "false" hides it)`).

### 3.5 — `#75` Cancel-while-running maps to CANCELLED is untested (minor · spec 21)

- **File:** `backend/tests/unit/test_compile_service.py`
- **Problem:** AC4 requires that a `CancelToken` cancelled **while the runner is
  running** maps to `CompileStatus.CANCELLED`. The only existing test
  (`test_cancelled_before_run`) cancels **before** `runner.run` is invoked
  (asserts `runner.calls == 0`), so the `if outcome.cancelled:` branch of
  `_build_result` (service.py ~line 139) is never exercised.
- **Fix:** Add a test where a `FakeRunner` is actually invoked and returns
  `RunOutcome(cancelled=True, ...)`. Assert `runner.calls == 1` (run was called)
  and that `_build_result`/the service result maps it to `CompileStatus.CANCELLED`.

### 3.6 — `#76` Cleanup on non-success outcomes is untested (minor · spec 21)

- **File:** `backend/tests/unit/test_compile_service.py`
- **Problem:** AC5 says that for **any** outcome (success/failure/timeout/cancel/
  system error), with `keep_workdir=False`, the workdir no longer exists on disk.
  Only `test_cleanup_default_removes_workdir` checks the success path.
- **Fix:** Add (ideally parametrized) assertions `assert not (tmp_path / str(cid)).exists()`
  after FAILURE (`exit_code=1`), TIMEOUT (`timed_out=True`), CANCELLED
  (`cancelled=True`), and SYSTEM_ERROR outcomes. Reuse the existing fixtures/fake
  runner pattern so the `finally`-block cleanup is verified for each path.

### 3.7 — `#93` Workdir-removal coverage per path, including cancel job (minor · spec 25)

- **Files:** `backend/tests/unit/test_compile_service.py`,
  `backend/tests/integration/test_compile_job.py`
- **Problem:** AC1 requires workdir removal asserted for **each** path. At service
  level only success is asserted (overlaps with `#76`). At job level,
  `test_cancel_during_run_trips_token` uses `CancelAwareService`, which never
  creates a real workdir, so the cleanup backstop is not actually exercised for the
  cancel path (contrast `test_workdir_removed_when_service_raises`, which uses
  `WorkdirCreatingService`).
- **Fix:** Service-level removal assertions are covered by `#76`. Additionally, make
  the **cancel job test** use a service that creates a **real** workdir (follow the
  `WorkdirCreatingService` pattern) so the cleanup backstop is exercised and assert
  the workdir directory does not exist after the cancel path completes. Keep the
  test deterministic (see `#94`).

### 3.8 — `#94` Cancel test uses real `asyncio.sleep` (nit · spec 25)

- **File:** `backend/tests/integration/test_compile_job.py`
- **Problem:** `test_cancel_during_run_trips_token` uses `await asyncio.sleep(0.05)`
  before cancelling and `CancelAwareService` polls `await asyncio.sleep(0.01)` up to
  200 iterations (worst case ~2 s of wall-clock). Spec 25 §5.2 audit item 4 asks to
  replace real sleeps in poll-style tests with deterministic control.
- **Fix:** Drive the cancel deterministically — e.g. have the fake service `await`
  an `asyncio.Event` that the test sets when it is ready to cancel (so `run` is
  in-flight at a known point), or use a controllable clock. Remove the fixed
  `asyncio.sleep(0.05)` pre-cancel wait and the polling sleep loop. The test must
  still prove the token is tripped while running. Coordinate with `#93` so the same
  refactored test both removes the sleeps **and** uses a real-workdir service.

### 3.9 — `#80` `run_compile` job `max_tries == 1` is untested (minor · spec 22)

- **Files:** `backend/tests/integration/test_compile_job.py`,
  `backend/src/inkstave/compile/worker.py` (read-only reference; value is already
  correct at ~line 112)
- **Problem:** AC4 requires asserting the job does not auto-retry (`max_tries=1`).
  `test_unexpected_exception_is_error_status` checks status/error_message but never
  asserts `max_tries`.
- **Fix:** Add a test that inspects `WorkerSettings.functions` (or the registered
  `func(...)` for `run_compile`) and asserts its `max_tries == 1`. No code change to
  `worker.py` is required for this issue.

### 3.10 — `#84` `COMPILE_RETENTION_SWEEP_S` is documented but never consumed (minor · spec 23)

- **Files:** `backend/src/inkstave/compile/worker.py`,
  `backend/src/inkstave/config.py`, `.env.example`
- **Problem:** `compile_retention_sweep_s` (config.py ~line 186; `.env.example`
  ~line 123) is documented as the cleanup-job interval, but the ARQ `cron(...)` for
  `cleanup_compile_outputs` is hardcoded to `minute=0` (worker.py ~line 121) and
  never reads the setting, so the setting has no runtime effect.
- **Fix (prefer making the setting live):** Derive the cron schedule from
  `settings.compile_retention_sweep_s`. For example, compute the set of minutes
  `{m for m in range(60) if m % max(1, sweep_s // 60) == 0}` when the interval is
  sub-hourly, or keep `minute=0` only when `sweep_s == 3600`. Implement a small,
  well-commented helper that converts the seconds setting into the `cron(...)`
  `minute`/`hour` arguments and use it in the `cron_jobs` list. If a faithful
  seconds-to-cron mapping is impractical, the alternative is to **rewrite the
  setting's docs** (config.py comment + `.env.example`) to state it is informational
  only — but the preferred fix is to make it actually control the schedule.

### 3.11 — `#108` Collab WS slow-client timed-put is never used (minor · spec 29)

- **Files:** `backend/src/inkstave/collab/ws/rooms.py`,
  `backend/src/inkstave/config.py` (setting already defined ~line 218),
  `backend/src/inkstave/collab/ws/components.py` (already plumbs the value ~lines 28, 40)
- **Problem:** Spec §5.2.4 requires a short timed put using
  `COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS`; on timeout, close with code 4408. The setting
  is defined and plumbed into `components.py` but `rooms.py` (`try_enqueue`, ~lines
  40–46) calls `put_nowait()` unconditionally, so the grace window is ignored and a
  slow socket is ejected immediately.
- **Fix:** In `rooms.py`, implement the timed put: use
  `await asyncio.wait_for(queue.put(item), timeout=slow_client_timeout_ms / 1000)`.
  On `asyncio.TimeoutError`, signal the caller to close the socket with WS close
  code **4408** (return/raise a sentinel the router/component already understands, or
  close it where the slow-client timeout value is available in `components.py`).
  Consume the configured value (do not hardcode). Keep the existing behaviour for
  the success path. Ensure existing collab WS tests stay green; add/extend a unit
  or integration test that proves a full queue triggers the timed wait and a 4408
  close (mock the queue to block).

### 3.12 — `#28` + `#218` Pydantic `extra="forbid"` on `ProjectRename` and `DocumentContentReplace` (minor · specs 11, 52)

- **Files:** `backend/src/inkstave/schemas/project.py`,
  `backend/src/inkstave/schemas/document.py`,
  `backend/tests/integration/test_hardening_55.py`
- **Problem:** `ProjectRename` (project.py ~line 28) and `DocumentContentReplace`
  (document.py ~line 22) extend plain `BaseModel`, not the shared `StrictModel`, so
  unknown body fields are silently ignored instead of returning 422. These are both
  request bodies (`PATCH /api/v1/projects/{id}` and
  `PUT /api/v1/projects/{id}/documents/{eid}`). The `test_request_models_forbid_extra_fields`
  guard list in `test_hardening_55.py` (~lines 155–175) omits both. Spec 52 §5.2.2
  requires every body model use `extra="forbid"` via `StrictModel`.
- **Fix:** Change `class ProjectRename(BaseModel)` → `class ProjectRename(StrictModel)`
  and `class DocumentContentReplace(BaseModel)` → `class DocumentContentReplace(StrictModel)`
  (import `StrictModel` from the shared base module as the sibling models do). Add
  both classes to the `request_models` list in
  `test_request_models_forbid_extra_fields` so CI enforces them. Confirm the
  endpoints now return 422 on an unknown extra key.

### 3.13 — `#217` Change-password endpoint has no rate limit (major · spec 52)

- **Files:** `backend/src/inkstave/api/routes/users.py`,
  `backend/src/inkstave/config.py`,
  `backend/tests/integration/test_hardening_55.py`
- **Problem:** `POST /api/v1/users/me/change-password` (users.py ~lines 82–103)
  verifies the current password but has **no** rate-limit dependency. Spec 52 §5.2.1
  requires an `auth_password` policy (5/hour, `user_or_ip`) on password-change
  endpoints. No `rate_limit_auth_password` setting exists. The `_SENSITIVE` set in
  `test_every_sensitive_route_is_rate_limited` omits this route, so CI misses the gap.
- **Fix:**
  1. Add a `rate_limit_auth_password` setting in `config.py` defaulting to the
     spec value (e.g. `"5/3600"`), following the existing rate-limit setting style.
  2. Add `dependencies=[Depends(rate_limit(...))]` to the change-password route in
     `users.py`, using the existing `rate_limit(...)` helper with the new policy and
     `user_or_ip` key strategy, matching how other sensitive auth routes wire it.
  3. Add `("POST", "/api/v1/users/me/change-password")` to the `_SENSITIVE`
     frozenset in `test_hardening_55.py` so
     `test_every_sensitive_route_is_rate_limited` enforces it.
  Document the new env var in `.env.example` if the other rate-limit vars are
  documented there.

### 3.14 — `#219` CORS/rate-limit env-var naming mismatch (nit · spec 52)

- **Files:** `.env.example`, `backend/src/inkstave/config.py`
- **Problem:** Spec 52 §5.8 names env vars `CORS_ALLOWED_ORIGINS` and
  `RATE_LIMIT_AUTH_LOGIN`, but the implementation uses `CORS_ORIGINS`
  (config.py ~line 38) and `RATE_LIMIT_LOGIN` (config.py ~line 95). config.py's
  error message even references `CORS_ALLOWED_ORIGINS` while the active var is
  `CORS_ORIGINS`. An operator following the spec table literally won't find the
  documented names.
- **Fix (prefer back-compat aliases):** Add Pydantic `AliasChoices`/validation
  aliases so the settings accept **both** the spec names (`CORS_ALLOWED_ORIGINS`,
  `RATE_LIMIT_AUTH_LOGIN`) and the current names (`CORS_ORIGINS`,
  `RATE_LIMIT_LOGIN`). Update `.env.example` to use the spec-canonical names with a
  note that the legacy names still work, and make the config.py error message
  consistent with the accepted name(s). Do not break existing `.env` files that use
  the current names. (If aliasing is impractical in the existing settings model,
  the minimal alternative is to fix `.env.example` + the error message so the
  documented and active names agree — but aliases are preferred.)

### 3.15 — `#243` `REDIS_URL` not in production-required guard (nit · spec 57)

- **File:** `backend/src/inkstave/config.py`
- **Problem:** Spec 57 §5.6 lists `REDIS_URL` as required in production, but
  `_guard_production_required` (config.py ~lines 310–316) only checks
  `DATABASE_URL`. `REDIS_URL` has a default so it is never truly empty, but a
  misconfigured prod deployment isn't caught at startup.
- **Fix:** Add `REDIS_URL` to the production-required check. Since it has a default,
  the meaningful guard is: in production, fail fast if `redis_url` is empty **or**
  still equals the localhost default (`redis://localhost:6379/0`). Add it to the
  validator's checked list with a clear error message, following the existing
  `_guard_production_required` style.

### 3.16 — `#127` Invite accept-URL base mismatch: `app_base_url` vs `frontend_url` (minor · spec 33)

- **Files:** `backend/src/inkstave/notifications/invite_hook.py`,
  `backend/src/inkstave/config.py`, `.env.example`
- **Problem:** Spec 33 §5.5 says the accept link base is `FRONTEND_URL`, and
  `.env.example` (~line 162) documents `FRONTEND_URL` as "base for invite accept
  links". But `invite_hook.py` (~line 36) builds the URL from
  `settings.app_base_url`, not `settings.frontend_url`. `frontend_url` is defined
  but unused for this; the docs contradict the code.
- **Fix (prefer making code match the documented intent):** Change
  `invite_hook.py` to build `accept_url` from `settings.frontend_url`:
  `accept_url = f"{settings.frontend_url.rstrip('/')}/invite/{raw_token}"`. Verify
  `frontend_url`'s comment in `config.py` and the `FRONTEND_URL` entry in
  `.env.example` remain accurate. Update any invite-hook test expectation that
  asserted the `app_base_url`-derived URL. (If using `app_base_url` is genuinely
  intended, the alternative is to remove the misleading `frontend_url` comment and
  correct `.env.example` — but matching the documented `FRONTEND_URL` base is
  preferred.)

### 3.17 — `#143` Missing history debounce-buffer unit tests (minor · spec 36)

- **File:** `backend/tests/unit/` (add a new unit test file, e.g.
  `backend/tests/unit/test_history_capture_36.py`)
- **Problem:** Spec 36 §8 explicitly requires fake-clock unit tests (no DB) for:
  (a) debounce timer re-arm when new updates arrive, (b) threshold-forced flush when
  the buffer reaches `HISTORY_FLUSH_MAX_BUFFER`, and (c) empty flush is a no-op.
  None exist; the forced-threshold path (capture.py ~lines 99–100) is unit-untested.
- **Fix:** Add a unit test file that drives the capture buffer directly (call
  `capture_update` / `flush_doc` or the equivalent public functions) with a fake or
  loop-controlled clock — **no Postgres**. Cover: (a) timer re-arms on each new
  update; (b) reaching `HISTORY_FLUSH_MAX_BUFFER` forces a flush with the
  threshold reason; (c) flushing an empty buffer is a no-op. Mock the offload/DB
  sink so the test stays in-memory and fast.

### 3.18 — `#207` Missing optional `agent_audit_cleanup` ARQ stub (minor · spec 49)

- **Files:** `backend/src/inkstave/agent/api/jobs.py`,
  `backend/src/inkstave/compile/worker.py`
- **Problem:** Spec 49 §5.1/§5.4 require an **optional** `agent_audit_cleanup` ARQ
  task stub, gated by retention config, **off by default**. `agent_audit_retention_days`
  exists but no cleanup function or cron entry does.
- **Fix:** Add an `agent_audit_cleanup` ARQ task in `agent/api/jobs.py` (a stub /
  no-op unless `agent_audit_retention_days` is configured to a positive value; when
  enabled, delete agent-audit rows older than the retention window — keep it minimal
  and structurally consistent with `cleanup_compile_outputs`). In `worker.py`,
  register the function and add a `cron(...)` entry **only when** the retention
  setting is set (off by default), or always register the function but make it a
  no-op when retention is unset. Keep it gated so the default deployment does
  nothing. Add a small unit/integration test proving it is a no-op when retention is
  unset and that it is registered.

### 3.19 — `#247` Missing unit tests for spec-59 schemas & account service (minor · spec 59)

- **Files:** `backend/tests/unit/` (add `backend/tests/unit/test_user_schemas_59.py`),
  `backend/src/inkstave/schemas/user.py` (read-only reference),
  `backend/src/inkstave/services/account.py` (read-only reference)
- **Problem:** Spec 59 §8 requires isolated unit tests for Pydantic schema
  validation and password/token-service invariants. The schemas
  (`EditorPreferences._clamp_font_size`, `UpdateProfileRequest`,
  `ChangePasswordRequest`, `ChangeEmailRequest`, `DeleteAccountRequest`) and the
  account service (`change_password`, `confirm_email_change`) are exercised only
  through the integration HTTP client.
- **Fix:** Add `backend/tests/unit/test_user_schemas_59.py` (and, if cleaner, a
  small `test_account_service_59.py` — both live under the in-scope `tests/unit/`
  dir) covering, in isolation:
  - `EditorPreferences` font-size clamping (below-min and above-max clamp to bounds)
    and enum/value validation;
  - `UpdateProfileRequest` display-name trimming and length bounds (reject too
    short/long);
  - password-policy reuse on `ChangePasswordRequest` (weak password rejected);
  - `account.change_password` verifies the current hash and rehashes (and rejects a
    wrong current password), and token hashing/expiry never stores raw tokens
    (for `confirm_email_change`). Use mocked repositories/hashers so no DB is
    needed; keep fast.

### 3.20 — `#126` Email pipeline is forward-scope (spec 39 built early) — DOC NOTE (minor · spec 33)

- **Files:** `backend/src/inkstave/mailer/jobs.py`,
  `backend/src/inkstave/mailer/sender.py`,
  `backend/src/inkstave/mailer/templates.py`,
  `backend/src/inkstave/notifications/invite_hook.py`
- **Problem:** Spec 33 wanted the invite email to be a no-op ARQ stub
  (`send_project_invite_email(invite_id)` that records intent but sends nothing).
  The implementation shipped the full spec-39 email pipeline early
  (`send_email_job`, `EmailEnqueuer`, `SmtpEmailSender`, `ConsoleEmailSender`,
  template rendering). This is **forward-scope over-delivery**, not a bug — spec 39
  legitimately supersedes it.
- **Fix:** **Do not remove the spec-39 pipeline.** Resolve this as a documentation
  note: add a short header comment in `mailer/jobs.py` (and, if helpful, in
  `invite_hook.py`) stating that the spec-39 email pipeline was implemented ahead of
  schedule during spec 33 and that the original "stub-only" requirement is
  superseded by spec 39. No behavioural change. (This keeps the in-scope mailer
  files touched only for a comment; do not modify SMTP/console sender behaviour.)

### 3.21 — `#22` `GET /users/me` returns `UserMe` not `UserPublic` — DOC NOTE (minor · spec 08)

- **Files:** `backend/src/inkstave/api/routes/users.py`,
  `backend/src/inkstave/schemas/user.py`
- **Problem:** Spec 08 §5.2 prescribed `UserPublic` for `GET /api/v1/users/me`, but
  the route returns `UserMe` (a strict superset added by spec 59:
  `avatar_url`, `editor_preferences`, `pending_email`). No consumer breaks; this is
  benign over-delivery that spec 59 intends.
- **Fix:** **Do not downgrade the response model.** Resolve as a documentation note:
  add a short comment near the `GET /me` route (and/or near `UserMe` in
  `user.py`) noting that `/me` was upgraded from `UserPublic` (spec 08) to `UserMe`
  in spec 59, and that `UserMe` is a strict superset. No behavioural change.

## 4. Acceptance criteria

Each is independently verifiable.

1. **`#3`** `grep -c '^CORS_ORIGINS=' .env.example` returns `1`.
2. **`#44`** `grep -c '^MAX_UPLOAD_BYTES=' .env.example` returns `1`, and the
   surviving comment reads "50 MiB".
3. **`#158`** `frontend/.env.example` contains `VITE_NOTIFICATIONS_POLL_INTERVAL_MS`.
4. **`#189`** `frontend/.env.example` contains `VITE_AGENT_ENABLED`.
5. **`#75`** A test invokes a runner that returns `RunOutcome(cancelled=True)` (run
   called) and asserts the result status is `CompileStatus.CANCELLED`.
6. **`#76`** Workdir-removal is asserted for failure, timeout, cancel, and
   system-error outcomes (not only success).
7. **`#93`** The cancel **job** test uses a service that creates a real workdir and
   asserts the workdir is removed after cancel.
8. **`#94`** The cancel job test contains no fixed `asyncio.sleep` poll loop; cancel
   is driven deterministically (e.g. an `asyncio.Event`).
9. **`#80`** A test asserts the registered `run_compile` job has `max_tries == 1`.
10. **`#84`** `compile_retention_sweep_s` either controls the cleanup cron schedule
    (referenced in `worker.py`) or its docs explicitly state it is informational —
    the documented behaviour matches reality.
11. **`#108`** `rooms.py` performs a timed `queue.put` using the slow-client timeout
    setting and closes slow sockets with code **4408**; a test proves the timeout
    path. The setting is actually consumed.
12. **`#28`/`#218`** `ProjectRename` and `DocumentContentReplace` extend
    `StrictModel`; both endpoints return 422 on an unknown extra field; both classes
    are in the `request_models` guard list.
13. **`#217`** `POST /api/v1/users/me/change-password` has a rate-limit dependency
    backed by a `rate_limit_auth_password` setting, and the route is in `_SENSITIVE`
    so `test_every_sensitive_route_is_rate_limited` covers it.
14. **`#219`** Settings accept the spec-canonical names (`CORS_ALLOWED_ORIGINS`,
    `RATE_LIMIT_AUTH_LOGIN`) and/or `.env.example` + the config error message use
    consistent names; legacy names still work.
15. **`#243`** `_guard_production_required` fails in production when `REDIS_URL` is
    empty or still the localhost default.
16. **`#127`** The invite accept URL is built from `settings.frontend_url` (or docs
    corrected to match `app_base_url`); code and `.env.example` agree.
17. **`#143`** New fake-clock unit tests cover timer re-arm, threshold-forced flush,
    and empty-flush no-op for history capture, with no DB.
18. **`#207`** An optional `agent_audit_cleanup` ARQ stub exists, gated by retention
    (off by default), with a test proving the no-op-when-unset behaviour.
19. **`#247`** New unit tests cover spec-59 schema validation and account-service
    invariants in isolation (no HTTP/DB roundtrip).
20. **`#126`** Mailer files carry a note that the spec-39 pipeline was delivered
    early and supersedes the spec-33 stub; no SMTP/console behaviour changed.
21. **`#22`** A note records that `/me` returns the `UserMe` superset (spec 59);
    response model unchanged.
22. The full test suite is green and runs in **< 2 minutes** (verified via
    `just test-timed`).

## 5. Test plan

> Keep the combined suite under 2 minutes. No real LaTeX/SMTP/Redis; mock/stub.

- **Stay green:** All existing tests in `test_compile_service.py`,
  `test_compile_job.py`, `test_hardening_55.py`, and the collab WS / mailer /
  account suites must continue to pass after the edits.
- **New / updated tests proving each fix:**
  - `test_compile_service.py`: cancelled-while-running → CANCELLED (`#75`);
    parametrized workdir-removal for failure/timeout/cancel/system-error (`#76`).
  - `test_compile_job.py`: `max_tries == 1` assertion (`#80`); cancel job test
    refactored to use a real-workdir service with no `asyncio.sleep` loop and a
    workdir-removed assertion (`#93`, `#94`).
  - `test_hardening_55.py`: add `ProjectRename` + `DocumentContentReplace` to the
    forbid-extra guard list; add change-password to `_SENSITIVE` (`#218`, `#217`).
    Add/confirm a 422-on-extra-field assertion for the two endpoints.
  - New `backend/tests/unit/test_history_capture_36.py`: fake-clock debounce tests
    (`#143`).
  - New `backend/tests/unit/test_user_schemas_59.py` (+ optional
    `test_account_service_59.py`): schema/service unit tests (`#247`).
  - Collab WS: a unit/integration test proving the timed-put + 4408 close (`#108`).
  - `agent_audit_cleanup` no-op-when-unset test (`#207`).
- **Performance/budget note:** All new tests are in-memory/mocked (fake clocks,
  stubbed sinks, mocked Redis/SMTP). Run `just test-timed` (xdist) to confirm the
  budget. Avoid adding real sleeps.

## 6. Definition of Done

- [ ] All 22 issues in §3 fixed (behaviour fixes applied; doc-note issues
      `#126`, `#22`, and any "docs-only" fallback for `#84`/`#127`/`#219` recorded
      as comments/`.env.example` edits).
- [ ] All acceptance criteria in §4 pass.
- [ ] New/updated tests in §5 written and green.
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] Edits limited to the files in §2 — no out-of-scope files touched.
- [ ] No Overleaf code copied; stack unchanged.
