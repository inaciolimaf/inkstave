# Spec 86 — Fix-pack: backend/frontend test & changelog gaps (batch 12) (requirements)

## 1. Summary

This fix-pack closes ten confirmed issues discovered by two independent
reviewers. They are predominantly **test-coverage and documentation gaps**
(plus one small frontend UI gap) spread across the observability stack
(spec 51 / 55), the projects refactor query-count suite (spec 15), the
performance/test-speed strategy (spec 53), the file-tree upload UI (spec 17),
the history UI detail header (spec 38), and the history refactor changelog
(spec 40). Each fix either adds the missing test the source spec requires,
improves the fidelity of an existing test fake, fixes a small UI omission, or
records the missing changelog rationale. No production behaviour should change
except the single small history detail-header UI addition (issue 152).

## 2. Files in scope

Edit **only** these files (the exact `payload.files` set). Do not touch any file
outside this list — other fix-packs may be running in parallel on other files.

- `backend/src/inkstave/observability/middleware.py`
- `backend/tests/conftest.py`
- `backend/tests/integration/test_observability_api.py`
- `backend/tests/integration/test_refactor_15.py`
- `docs/refactor/0015-projects-files.md`
- `docs/refactors/40-history-notifications.md`
- `frontend/src/features/file-tree/file-tree-upload.test.tsx`
- `frontend/src/features/history/HistoryDiffView.tsx`
- `frontend/src/features/history/HistoryPanel.tsx`

Restrict edits: you may add or modify test routes/fixtures **inside the
in-scope test files only**. If the route-template regression test (issue 232)
needs a parameterized test route, register it from within
`test_observability_api.py` (e.g. on the app under test) rather than editing the
production router. `middleware.py` is in scope only for a tiny, optional
non-behavioural adjustment if the test reveals one; prefer testing the existing
`_route_template` as-is.

## 3. Issues to fix

### Issue 213 — AC3 user_id auto-propagation not integration-tested (MAJOR)

- **Source spec:** 51-observability
- **Severity:** major (adjusted: major)
- **File(s):** `backend/tests/integration/test_observability_api.py`
- **Problem:** Spec 51 AC3 (spec.md lines 298–300) requires that a log line
  emitted anywhere inside a request *after auth has resolved* automatically
  includes the same `request_id` **and** the resolved `user_id`, without the call
  site passing them explicitly. The only finish-log integration test
  (`test_observability_api.py:56–73`) hits the **unauthenticated**
  `GET /api/v1/openapi.json` and asserts `request_id/method/path/status` — it
  never asserts `user_id`. The formatter-level `user_id` is unit-tested
  (`test_observability.py:54–66`) but the end-to-end auth→log auto-propagation in
  a real authenticated request is not integration-tested.
- **Fix to apply:** Add an integration test that authenticates a user (reuse the
  existing auth/token fixtures used elsewhere in the integration suite), calls an
  **authenticated** route, captures the finish/handler log line, and asserts the
  log line automatically includes the resolved `user_id` (matching the
  authenticated user's id) without the handler passing it explicitly. Assert
  `request_id` is also present and consistent.

### Issue 215 — FakeRedisRaising does not simulate a real ConnectionError (MINOR)

- **Source spec:** 51-observability
- **Severity:** minor
- **File(s):** `backend/tests/conftest.py`,
  `backend/tests/integration/test_observability_api.py`
- **Problem:** `conftest.py:347–351` `FakeRedisRaising` defines only
  `async def ping(self)`. `metrics.py:140` `sample_queue_depth` calls
  `await redis.zcard(queue)`, which on `FakeRedisRaising` raises `AttributeError`
  (no such method), caught by the broad `except Exception`. The fail-soft
  behaviour is therefore verified, but the fake exercises a *missing-attribute*
  error rather than a realistic Redis **connection failure**.
- **Fix to apply:** Give `FakeRedisRaising` `async def zcard(...)` and
  `async def llen(...)` methods (and any other method the metrics/readyz paths
  call) that raise a real connection error
  (`redis.exceptions.ConnectionError` / `aioredis.ConnectionError`) so the
  AC12 metrics test exercises the genuine connection-failure path. Keep `ping`
  raising the same connection error so the readyz tests remain meaningful.

### Issue 225 — Template-DB strategy deviates from spec 53 AC2 wording (MINOR)

- **Source spec:** 53-performance-test-speed
- **Severity:** minor
- **File(s):** `backend/tests/conftest.py`
- **Problem:** Spec 53 AC2 states "each xdist worker uses its own DB cloned from a
  once-migrated template, migrations run once". The implementation
  (`conftest.py` `_template_db` fixture, line ~199/220) has **each** worker create
  its own DB and run `command.upgrade(..., 'head')` independently — migrations run
  per worker, not once. The deviation is recorded in ADR-0053 with a reasoned
  trade-off, but AC2's literal "migrations run once" criterion is unmet.
- **Fix to apply:** Reconcile the deviation explicitly. Preferred minimal fix:
  add a clear, source-referencing comment at the `_template_db` fixture noting
  that spec 53 AC2's "migrations run once" wording is **knowingly** traded for
  per-worker migration per ADR-0053, with a one-line rationale, so the deviation
  is documented at the code site (not only in the ADR). (Implementing the full
  `CREATE DATABASE ... TEMPLATE` clone is acceptable but optional and riskier;
  if you do it, keep the suite green and under budget.)

### Issue 233 — /readyz recovery half of spec 55 AC4 untested (MINOR)

- **Source spec:** 55-refactor-hardening
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_observability_api.py`
- **Problem:** Spec 55 AC4 (spec.md 190–192) requires "/readyz truly fails (503)
  when a dependency is down **and recovers**".
  `test_healthz_always_ok_and_readyz_503_when_redis_down`
  (`test_observability_api.py:102–110`) sets `app.state.redis = FakeRedisRaising()`,
  asserts `/readyz` returns 503 and `/healthz` still 200, but never restores a
  healthy Redis and re-asserts `/readyz` returns 200. The "recovers" half is
  untested.
- **Fix to apply:** Extend the test: after asserting 503, restore a working Redis
  on `app.state.redis` (the normal fake used elsewhere) and assert
  `GET /readyz` returns 200 with `checks.redis == "ok"` (matching the readyz
  response shape used in the codebase).

### Issue 214 — Test profile does not force LOG_LEVEL=warning (MINOR)

- **Source spec:** 51-observability
- **Severity:** minor
- **File(s):** `backend/tests/conftest.py`
- **Problem:** Spec 51 §5.6 (spec.md 260–262) mandates that the test profile force
  `LOG_LEVEL=warning` (plus `LOG_FORMAT=json`, `OTEL_ENABLED=false`,
  `METRICS_PUBLIC=true` — the latter three already satisfied by config defaults).
  `conftest.py` overrides (lines ~66–80) set only the vestigial `LOG_JSON=false`
  (dead since `log.py` now keys off `log_format`) and **no** `LOG_LEVEL`, so tests
  run at the `INFO` default (`config.py:32`), emitting more log output than the
  spec intends.
- **Fix to apply:** Add `"LOG_LEVEL": "WARNING"` to the `conftest.py` settings
  overrides dict and drop the dead `LOG_JSON` entry. Confirm no test relies on
  INFO-level log capture (the observability finish-log tests capture via the
  configured logger/handler, not the threshold; if any such test needs INFO it
  must set it locally — but none should).

### Issue 232 — http.path route-template cardinality/PII case not regression-tested (MINOR)

- **Source spec:** 55-refactor-hardening
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_observability_api.py`,
  `backend/src/inkstave/observability/middleware.py`
- **Problem:** Spec 55 §5.1 requires "`http.path` is the route template (never a
  raw id-bearing URL — a cardinality/PII risk)" and the changelog claims this is
  "verified correct". But the only `http.path` assertion
  (`test_observability_api.py:69`) uses the **static** route
  `/api/v1/openapi.json`, which has no path params. `_route_template`
  (`middleware.py:29`) handles parameterized routes, but the parameterized case
  (the PII-sensitive one) is not regression-tested, so a future regression would
  go undetected.
- **Fix to apply:** Add a test that attaches a parameterized route to the app
  under test (e.g. `GET /_test/items/{item_id}`) **from inside the test file**,
  calls it with a concrete id (e.g. a UUID), captures the finish log, and asserts
  the log's `http.path` equals the **template** form `/_test/items/{item_id}`
  (not the raw id). Do not modify the production router. Touch `middleware.py`
  only if the test surfaces a genuine bug in `_route_template`; otherwise leave it
  unchanged.

### Issue 59 — Upload conflict test missing (MINOR)

- **Source spec:** 17-file-tree-ui
- **Severity:** minor
- **File(s):** `frontend/src/features/file-tree/file-tree-upload.test.tsx`
- **Problem:** Spec 17 §8 requires an "Upload: conflict prompt" test. The upload
  test file has exactly one `it(...)` block (line 45) covering only the success /
  progress path; `grep` for `conflict` returns 0 matches. The 409/name_conflict
  surfacing is untested.
- **Fix to apply:** Add a test that mocks the upload throwing a
  `409`/`name_conflict` `UploadError` and asserts the user-facing conflict
  message/prompt appears (matching whatever the upload component renders on
  `name_conflict`). Use the same mocking/render harness as the existing success
  test in this file.

### Issue 152 — History detail-header label badges missing (MINOR)

- **Source spec:** 38-history-ui
- **Severity:** minor
- **File(s):** `frontend/src/features/history/HistoryPanel.tsx`,
  `frontend/src/features/history/HistoryDiffView.tsx`
- **Problem:** Spec 38 §5.3.4 (line 102) states "Labels appear as badges on their
  version row **and in the detail header**." The right-side detail region
  (`HistoryPanel.tsx:85–95`) renders only `RestoreVersionButton` +
  `HistoryDiffView`; `HistoryDiffView` has no label/Badge rendering. The
  detail-header badges are absent.
- **Fix to apply:** Add a detail-header region for the currently selected version
  above (or within) the diff view that renders that version's label badges,
  reusing the same `Badge` component/styling already used on the timeline rows.
  Wire it from the selected version's labels in `HistoryPanel` (or add a small
  header to `HistoryDiffView` fed by props). Keep it consistent with the existing
  row-badge presentation.

### Issue 46 — file-get N+1 query-count coverage missing (MAJOR → adjusted MINOR)

- **Source spec:** 15-refactor-projects
- **Severity:** major (adjusted: minor — missing test only, no runtime defect)
- **File(s):** `backend/tests/integration/test_refactor_15.py`,
  `docs/refactor/0015-projects-files.md`
- **Problem:** Spec 15 AC3 / §8 require query-count assertions proving no N+1 on
  tree-list, project-list, **and document/file-get**. `test_refactor_15.py`
  (lines ~43–84) covers tree-list, project-list, and document-get, but has **no
  file-get** query-count test (the only `files/` reference is a service-level
  404 test, not an HTTP query-count assertion). The changelog F-005 row also
  omits file-get.
- **Fix to apply:** Add a query-count integration test that GETs a binary file
  (e.g. `GET /api/v1/projects/{pid}/files/{eid}`, matching the existing route)
  using the same `query_counter`/statement-counting helper the sibling tests use,
  and asserts a bounded, non-scaling statement count (no N+1). Add `file-get` to
  the F-005 row in `docs/refactor/0015-projects-files.md` so the changelog matches
  reality.

### Issue 160 — spec-40 changelog missing spec-38 (history UI) §5.1 checklist (MAJOR)

- **Source spec:** 40-refactor-history
- **Severity:** major
- **File(s):** `docs/refactors/40-history-notifications.md`
- **Problem:** Spec 40 §5.1 enumerates explicit spec-38 (history UI) review items
  (loading/empty/error states, pagination correctness, selection-model bugs, diff
  fallback rendering, restore confirmation copy + flow, no direct editor mutation,
  a11y: markers not colour-only + focus trapping). AC1 (spec.md:124) requires the
  §5.1 checklist to be "executed and its findings recorded … with a fix/skip
  decision and rationale for each." `docs/refactors/40-history-notifications.md`
  has **zero** spec-38 rows in Applied Fixes, **zero** in Deliberately Skipped,
  and the "Verified correct" row lists only backend items. AC1 is unmet for
  spec 38.
- **Fix to apply:** Add the spec-38 (history UI) review items to the changelog
  with, for each enumerated item, a fix/skip decision and a short rationale (or a
  "verified correct" entry naming the covering test/behaviour). Place them in the
  appropriate existing tables (Applied / Deliberately Skipped / Verified correct).
  This is a documentation-only fix; do not change history UI code here (the badge
  UI change is covered separately by issue 152, in different files).

## 4. Acceptance criteria

1. An integration test authenticates a user, calls an authenticated route, and
   asserts the captured finish/handler log line automatically contains the
   resolved `user_id` (equal to the authenticated user) and a consistent
   `request_id` (issue 213).
2. `FakeRedisRaising` exposes `zcard`/`llen` (and `ping`) that raise a real
   `ConnectionError`; the AC12 metrics-down test passes by exercising that
   connection-failure path, not an `AttributeError` (issue 215).
3. The `_template_db` fixture documents, at the code site, the knowing deviation
   from spec 53 AC2's "migrations run once" wording per ADR-0053 (or implements a
   true once-migrated template clone) (issue 225).
4. The readyz test, after asserting 503 with a failing Redis, restores a healthy
   Redis and asserts `GET /readyz` returns 200 with `checks.redis == "ok"`
   (issue 233).
5. The test profile forces `LOG_LEVEL=WARNING` in `conftest.py` overrides and the
   dead `LOG_JSON` entry is removed; the suite still passes (issue 214).
6. A test exercises a parameterized route and asserts the finish-log `http.path`
   equals the route-template form (e.g. `/_test/items/{item_id}`), not the raw id;
   the production router is unchanged (issue 232).
7. `file-tree-upload.test.tsx` contains a test that mocks a 409/name_conflict
   `UploadError` and asserts the user-facing conflict message/prompt appears
   (issue 59).
8. The history detail region renders the selected version's label badges in a
   detail header, using the same Badge styling as timeline rows (issue 152).
9. `test_refactor_15.py` contains a file-get query-count assertion proving no
   N+1, and the F-005 changelog row lists file-get (issue 46).
10. `docs/refactors/40-history-notifications.md` records each spec-38 (history UI)
    §5.1 review item with a fix/skip/verified decision and rationale (issue 160).

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Slow work (LaTeX, real LLM, real Redis) is stubbed/faked as already done.

- **Existing green:** Run `backend` pytest (unit + integration) and the
  `frontend` Vitest suite before and after. They must remain green.
- **New / updated (backend, pytest):**
  - New authenticated finish-log test asserting auto `user_id` propagation
    (issue 213).
  - Updated AC12 metrics-down test using the improved `FakeRedisRaising`
    (issue 215).
  - Extended readyz test asserting 503-then-recovery to 200 (issue 233).
  - New parameterized-route `http.path` template assertion (issue 232).
  - New file-get query-count assertion in `test_refactor_15.py` (issue 46).
  - `conftest.py` now forces `LOG_LEVEL=WARNING`; confirm no test relies on INFO
    capture (issue 214).
- **New / updated (frontend, Vitest):**
  - New upload-conflict test in `file-tree-upload.test.tsx` (issue 59).
  - Updated/added test (or existing render test) covering the detail-header label
    badges in the history panel (issue 152) — assert a badge renders in the
    detail region for a labelled selected version.
- **Docs (no test):** issues 225 (comment), 46 changelog row, 160 changelog
  entries are verified by inspection against the acceptance criteria.
- **Performance/budget note:** All additions are unit/integration-level with
  faked Redis/DB and mocked uploads; no real compile or LLM calls. The suite must
  remain under 2 minutes.

## 6. Definition of Done

- [ ] All ten issues (213, 215, 225, 233, 214, 232, 59, 152, 46, 160) addressed
      as described in §3.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 are written and green; existing tests stay
      green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (`ruff`/`mypy` for backend; ESLint/Prettier/
      `tsc` for frontend).
- [ ] Only files listed in §2 were modified; no production router changes for the
      route-template test.
- [ ] No Overleaf code copied.
