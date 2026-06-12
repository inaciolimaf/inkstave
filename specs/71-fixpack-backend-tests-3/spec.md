# Spec 71 — Fix-Pack: Backend & Tests 3 (requirements)

## 1. Summary

This fix-pack closes **9 confirmed issues** validated by two independent
reviewers across specs 02, 11, 23, 29, 38, and 51. The headline item is a
**critical** frontend bug: the history "diff too large" fallback is unreachable
in production because the API client throws on the HTTP 413 the backend returns,
and a mis-mocked unit test hides the failure. The remaining items harden test
coverage (retention batch bound, terminal-event ordering, the cleanup job
itself, cross-user error code, the awareness-snapshot handshake branch, a
missing `RequestIdMiddleware` unit test), add a missing typed `listLabels`
client method, and fill the observability docs reference.

**Severity breakdown (adjusted):** 1 critical, 0 major, 7 minor, 1 nit.

## 2. Files in scope

Edit **only** these files (the exact payload set). Do not touch anything else.

- `backend/src/inkstave/compile/retention.py`
- `backend/tests/integration/test_app.py`
- `backend/tests/integration/test_collab_ws_api.py`
- `backend/tests/integration/test_compile_outputs.py`
- `backend/tests/integration/test_projects_api.py`
- `backend/tests/unit` (add a new unit test file here, e.g.
  `backend/tests/unit/test_request_id_middleware.py`)
- `docs/adr/0051-observability.md`
- `frontend/src/features/history/HistoryDiffView.test.tsx`
- `frontend/src/features/history/api.ts`
- `frontend/src/lib/api-client.ts`

> If a fix appears to require a file outside this list, **stop and report**
> instead of editing it. In particular: `backend/src/inkstave/compile/jobs.py`,
> `frontend/src/features/history/HistoryDiffView.tsx`, and the collab router are
> **out of scope** — verify and test around their current behaviour, do not edit
> them. The only production source files you may edit are
> `backend/src/inkstave/compile/retention.py`, `frontend/src/features/history/api.ts`,
> and `frontend/src/lib/api-client.ts`.

## 3. Issues to fix

### Issue 150 — History diff 413 makes "too large" fallback unreachable (CRITICAL)

- **Source spec:** 38-history-ui
- **Severity:** critical
- **Files:** `frontend/src/features/history/api.ts`,
  `frontend/src/lib/api-client.ts`,
  `frontend/src/features/history/HistoryDiffView.test.tsx`

**Problem.** The backend returns **HTTP 413** for too-large diffs, with a JSON
body that includes `too_large: true` (`history.py:125` —
`code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if result.too_large else status.HTTP_200_OK`).
But `apiClient.get` does `if (!res.ok) throw await toApiError(res)`
(`api-client.ts:142`); a 413 is not `ok`, so `getDiff` **throws** instead of
returning `{ tooLarge: true }`. `HistoryDiffView` only checks
`query.data.tooLarge`; because the query rejects, the error branch
(`query.isError`) renders instead and the fallback message
"This version is too large to diff." (HistoryDiffView.tsx ~line 92) is
**unreachable in production**. AC5 of spec 38 is broken for the `too_large`
case. The unit test masks this by mocking `getDiff` to **resolve** with
`{ tooLarge: true }` instead of **reject** with a 413 (`HistoryDiffView.test.tsx:62`).

**Fix to apply.**
1. In `frontend/src/features/history/api.ts`, make `getDiff` resilient to the
   413: wrap the `apiClient.get` call so that when the thrown `ApiError` has
   `status === 413` (and/or its body carries `too_large: true`), `getDiff`
   **returns** the too-large diff result (`{ tooLarge: true, ... }`) instead of
   re-throwing. All other errors must continue to propagate unchanged. Keep the
   returned shape identical to the normal `tooLarge` mapping the view already
   consumes (so `HistoryDiffView` keeps working with no change to that file).
2. Ensure `frontend/src/lib/api-client.ts` exposes enough information for that
   branch to work — the thrown `ApiError` must carry the HTTP `status` (413) and,
   if available, the parsed JSON body (so `too_large` can be read). If the
   existing `ApiError`/`toApiError` already preserves `status` and body, prefer
   reading from it and make **no** behavioural change to `api-client.ts` beyond
   what is strictly required; if `status`/body is not currently exposed, add it
   minimally (a `status` number field and the parsed body) without altering the
   throw-on-`!ok` contract for other callers.
3. Update `HistoryDiffView.test.tsx`: change the "too large" case so the mock
   **rejects** with a 413 `ApiError` (matching real backend behaviour) rather
   than resolving with `{ tooLarge: true }`, and assert that the
   "too large to diff" fallback message renders (not the generic error state).
   This test must fail against the old `getDiff` and pass after the fix.

> Do **not** edit `HistoryDiffView.tsx` or the backend `history.py`. The fix
> lives entirely in `api.ts` (+ minimal `api-client.ts` support) and the test.

### Issue 153 — Missing typed `listLabels` (GET) client method

- **Source spec:** 38-history-ui
- **Severity:** minor
- **Files:** `frontend/src/features/history/api.ts`

**Problem.** Spec 38 §5.2 requires typed client methods + TS types for
**GET/POST/DELETE** `/history/labels`. Only `createLabel` (POST) and
`deleteLabel` (DELETE) exist (`api.ts:121-138`); the GET list-labels method is
missing.

**Fix to apply.** Add a typed `listLabels(projectId, docId)` function that calls
`GET .../docs/{docId}/history/labels` and maps each wire item through the
existing `toLabel` mapper, returning the array of typed labels. Mirror the
naming, parameter order, and mapping style of the existing `createLabel` /
`deleteLabel`. Add a focused test if the file has co-located tests for the other
label methods; otherwise an exported, typed function matching the spec schema is
sufficient.

### Issue 86 — Retention batch bound never exercised

- **Source spec:** 23-output-storage
- **Severity:** minor
- **Files:** `backend/tests/integration/test_compile_outputs.py`

**Problem.** Spec 23 AC10 requires that "the batch is bounded". The two
retention tests pass `batch=10` with at most 4 seeded rows, so the SQL `LIMIT`
is never the binding constraint — the tests would pass even if `LIMIT` were
removed.

**Fix to apply.** Add a test that seeds **more retention-eligible compiles than
the batch** (e.g. seed 5 eligible compiles, call with `batch=3`) and assert
**exactly 3** ids are returned, proving the `LIMIT` clause binds.

### Issue 87 — AC2 terminal-event ordering not asserted

- **Source spec:** 23-output-storage
- **Severity:** minor
- **Files:** `backend/tests/integration/test_compile_outputs.py`

**Problem.** AC2 requires outputs be persisted **before** the terminal status
event is published. `jobs.py` orders this correctly (persist at ~165, publish at
~195), but `test_job_persists_outputs_and_cleans_workdir` only checks final
state, not the ordering invariant.

**Fix to apply.** In the job-level test, wrap `publish_status` and the persist
step (e.g. the persist hook / output-store write) in spies that record call
order (append to a shared list, or record monotonic counters). Assert that the
persist completes **before** the terminal `publish_status` is invoked. Do not
edit `jobs.py`; instrument via mocks/spies on its collaborators within the test.

### Issue 85 — `cleanup_compile_outputs` job not directly tested

- **Source spec:** 23-output-storage
- **Severity:** minor
- **Files:** `backend/tests/integration/test_compile_outputs.py`,
  `backend/src/inkstave/compile/retention.py`

**Problem.** AC10 is currently exercised only by calling
`repo.list_compiles_for_retention(...)` directly; the actual job function
`cleanup_compile_outputs` in `retention.py` is never invoked, so a bug in its
`ctx['make_output_store']` wiring or its `session.commit()` would go undetected.

**Fix to apply.** Add an integration test that:
1. Builds an ARQ-style `ctx` dict containing the same `session` and a
   `make_output_store` callable the job expects.
2. Seeds compiles (with stored outputs) **beyond** the retention window.
3. Calls `cleanup_compile_outputs(ctx)`.
4. Asserts that both the **storage objects** and the **`compile_outputs` rows**
   are deleted for the evicted compiles, while retained compiles keep theirs.

`retention.py` is in scope **only** to read/confirm the `ctx` contract; do not
change its behaviour unless a genuine bug surfaces. If you do touch
`retention.py`, keep the change minimal and explained.

### Issue 29 — Cross-user 404 error code not asserted

- **Source spec:** 11-project-model-crud
- **Severity:** minor
- **Files:** `backend/tests/integration/test_projects_api.py`

**Problem.** `test_ownership_is_existence` asserts only `status_code == 404` for
cross-user GET/PATCH/DELETE, not the error code. AC7 requires both the 404 and
`error.type == "project_not_found"`.

**Fix to apply.** Inside the cross-user loop in `test_ownership_is_existence`,
add `assert resp.json()["error"]["type"] == "project_not_found"` (matching the
assertion already used on the delete-then-access path) for each verb that
returns a JSON body.

### Issue 110 — Awareness-snapshot handshake branch untested

- **Source spec:** 29-collab-websocket
- **Severity:** minor
- **Files:** `backend/tests/integration/test_collab_ws_api.py`

**Problem.** AC3 requires the client to receive a server Sync Step 1 **and (if
present) an awareness snapshot** before sending anything. The existing test only
asserts the first frame is `SyncStep1`; the snapshot branch (router.py:303-305,
guarded by `if snapshot is not None`) is never exercised.

**Fix to apply.** Add a test that **pre-populates awareness** for the room
(so a snapshot exists), opens the websocket, reads the first frame
(`SyncStep1`), then reads the **second** frame and asserts it is the awareness
snapshot (`AwarenessMessage`) — verifying the snapshot is delivered before the
client sends anything. Reuse existing helpers/fixtures for seeding awareness;
do not edit the router.

### Issue 7 — Missing `RequestIdMiddleware` unit test

- **Source spec:** 02-backend-foundation
- **Severity:** minor
- **Files:** `backend/tests/unit` (new file),
  `backend/tests/integration/test_app.py`

**Problem.** Spec 02 §8 explicitly requires a **unit** test:
"`RequestIdMiddleware` generates an id when absent and reuses a provided id."
This behaviour is only covered at integration level
(`test_app.py::test_request_id_generated_and_echoed`). The unit-level test
(driving the middleware over a raw ASGI scope, no full app wiring) is missing.

> Note: the payload's secondary "dead code path" claim about `test_logging.py`
> was found **inaccurate** by the reviewers — do **not** act on it. Only add the
> missing unit test.

**Fix to apply.** Add a new unit test (e.g.
`backend/tests/unit/test_request_id_middleware.py`) that drives
`RequestIdMiddleware` directly over a raw/minimal ASGI scope (no full FastAPI
app, no httpx client) and asserts:
1. When the request has **no** request-id header, the middleware **generates**
   an id and the response carries it.
2. When the request **provides** an id header, the middleware **reuses/echoes**
   that exact id on the response.

Leave `test_app.py` as-is unless a trivial touch is needed; the integration test
there should remain green and continues to cover the full-app path.

### Issue 216 — Observability docs missing field/metric reference (NIT)

- **Source spec:** 51-observability
- **Severity:** nit
- **Files:** `docs/adr/0051-observability.md`

**Problem.** The DoD says "observability ADR + field/metric reference added under
docs/". The ADR has narrative decisions and the Prometheus scrape-config snippet
but **does not reproduce** the full log-field schema table (spec §5.2.1) or the
metric catalogue table (spec §5.3). Readers must consult the spec instead.

**Fix to apply.** Add to `docs/adr/0051-observability.md`:
1. A **log-field schema table** listing each structured-log field with name,
   type, and description (mirroring spec 51 §5.2.1).
2. A **metric catalogue table** listing each emitted metric with name, type
   (counter/gauge/histogram), labels, and description (mirroring spec 51 §5.3).

Source the exact field/metric names from the live code (e.g. the observability
log/metrics modules referenced by spec 51) so the tables match what is actually
emitted. This is documentation only — no code change.

## 4. Acceptance criteria

1. **(Issue 150)** With `getDiff` exercised against a backend response of HTTP
   413 + `{ too_large: true }`, `getDiff` **resolves** with a too-large result
   (`tooLarge: true`) rather than rejecting; `HistoryDiffView` renders the
   "too large to diff" fallback. All other HTTP errors from `getDiff` still
   reject. The updated `HistoryDiffView.test.tsx` mocks a **413 rejection** and
   asserts the fallback message; it fails against the pre-fix `getDiff`.
2. **(Issue 153)** A typed `listLabels(projectId, docId)` exists in
   `history/api.ts`, calls GET `/history/labels`, and maps results via
   `toLabel`.
3. **(Issue 86)** A retention test seeds N > batch eligible compiles and asserts
   exactly `batch` ids are returned.
4. **(Issue 87)** The job test asserts persist happens **before** the terminal
   `publish_status` via recorded call order.
5. **(Issue 85)** A test invokes `cleanup_compile_outputs(ctx)` end-to-end and
   asserts both storage objects and `compile_outputs` rows are removed for
   evicted compiles (and retained for kept ones).
6. **(Issue 29)** `test_ownership_is_existence` asserts
   `error.type == "project_not_found"` for cross-user access.
7. **(Issue 110)** A handshake test seeds pre-existing awareness and asserts the
   second received frame is the awareness snapshot.
8. **(Issue 7)** A new unit test drives `RequestIdMiddleware` over a raw ASGI
   scope and asserts id generation when absent and reuse when provided.
9. **(Issue 216)** `docs/adr/0051-observability.md` contains a log-field schema
   table and a metric catalogue table matching the emitted fields/metrics.
10. All pre-existing tests stay green; the full suite runs in < 2 minutes.

## 5. Test plan

> All tests combined must keep the suite under 2 minutes. No new slow (LaTeX/LLM)
> work is introduced; everything is mocked/seeded against the test DB or in-memory.

- **Frontend (Vitest):**
  - Update `HistoryDiffView.test.tsx` "too large" case to mock a **413
    rejection** and assert the fallback message renders. Confirm it fails before
    the `api.ts` fix and passes after.
  - If `history/api.ts` has co-located tests, add one for `getDiff` 413 →
    `{ tooLarge: true }` and one for `listLabels` shape.
- **Backend (pytest):**
  - `test_compile_outputs.py`: add batch-bound test (N > batch), ordering-spy
    test (persist before publish), and the end-to-end `cleanup_compile_outputs`
    job test.
  - `test_projects_api.py`: add the `project_not_found` error-code assertion.
  - `test_collab_ws_api.py`: add the awareness-snapshot handshake test.
  - `backend/tests/unit/test_request_id_middleware.py`: new raw-ASGI unit test.
- **Docs:** no test; verify the tables render and field/metric names match code.
- **Performance/budget note:** all additions are fast unit/integration tests;
  run `just test-timed` to confirm the suite stays < 2 minutes.

## 6. Definition of Done

- [ ] All 9 issues in §3 resolved; none invented, none dropped.
- [ ] Issue 150 (critical) fixed in `api.ts` (+ minimal `api-client.ts` support)
      and proven by an updated rejecting-413 test; `HistoryDiffView.tsx` and the
      backend untouched.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green.
- [ ] No files edited outside §2.
- [ ] Full suite runs in < 2 minutes (`just test-timed`).
- [ ] Lint/format/type-check clean (ruff + pyright on backend; ESLint + tsc on
      frontend).
- [ ] No Overleaf code copied; stack unchanged.
