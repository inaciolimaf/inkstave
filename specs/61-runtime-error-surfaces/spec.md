# Spec 61 — Runtime Error Surfaces (requirements)

## 1. Summary

This spec makes the app fail gracefully on the representative HTTP error cases
and proves it with fast, deterministic tests. It fixes one confirmed runtime bug:
the history **diff endpoint** returns `HTTP 413` with a JSON body
`{from, to, binary, too_large: true, hunks: []}`, but the frontend API client
throws on **any** non-ok response, so `getDiff` raises an `ApiError` before the
`too_large` flag is ever read — the history diff view therefore shows the generic
"Couldn't load the diff" error instead of the intended "too large" state. We make
`getDiff` map a 413 to a structured `tooLarge` result, verify the backend uniform
error envelope across status codes, and confirm request-timeout handling returns a
clean error rather than an unhandled throw.

## 2. Context & dependencies

- **Depends on:** spec 02 (uniform error envelope + exception handlers), spec 09
  (frontend `api-client.ts`, `ApiError`), spec 37 (history diff API returning 413
  + `too_large`), spec 38 (history UI: `HistoryDiffView`, `getDiff`).
- **Unlocks:** spec 64 (frontend resilience) builds on the same "no unhandled
  throw" guarantee for views.
- **Affected areas:** frontend (`frontend/src/features/history/api.ts`), backend
  (verification-only tests against existing error handlers and the diff route),
  tests (frontend Vitest + backend pytest).

## 3. Goals

- `getDiff` returns a structured `{ tooLarge: true }` `DiffResult` when the diff
  route responds `413` (does **not** throw). The existing `HistoryDiffView`
  "This version is too large to diff." branch then renders.
- A Vitest test proves `getDiff` maps a mocked 413 (with the real body shape) to
  `tooLarge: true` and the history diff view renders the "too large" state.
- A pytest assertion confirms the diff route returns status `413` **and** a JSON
  body containing `too_large: true` (full diff shape, not an error envelope) when
  the reconstructed text exceeds `history_diff_max_bytes`.
- A pytest assertion confirms the uniform error envelope shape across the
  representative error statuses: `401`, `403`, `404`, `409`, `413`, `422`, `500`.
- A test confirms a request timeout / network failure surfaces as a clean,
  catchable error rather than an unhandled rejection.

## 4. Non-goals (explicitly out of scope)

- No change to the error-envelope schema or to which status codes map to which
  `AppError` subclass — this spec only **verifies** them.
- No change to the diff route response contract (413 + `too_large` body stays).
- No new UI beyond what `HistoryDiffView` already renders (the "too large"
  branch already exists; we only make it reachable).
- No real network, LLM, or LaTeX compile in tests.
- No global retry/backoff policy or circuit breaker (later hardening work).

## 5. Detailed requirements

### 5.1 Data model (if any)

None. No schema changes, no Alembic migration.

### 5.2 Backend / API (if any)

**Verification only — no behavioural change.** Confirm and lock down current
behaviour with tests:

- Uniform error envelope is defined in
  `/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/errors.py`:
  - `ErrorBody{ type: str, message: str, details: list[dict]|None, request_id: str|None }`
  - `ErrorEnvelope{ error: ErrorBody }`
  - `AppError` subclasses: `BadRequestError(400)`, `UnauthorizedError(401)`,
    `ForbiddenError(403)`, `NotFoundError(404)`, `ConflictError(409)`,
    `GoneError(410)`, `RateLimitError(429)`; plus service-level
    `ContentTooLargeError(413, "content_too_large")` in
    `backend/src/inkstave/services/document_service.py` and
    `FileTooLargeError(413, "file_too_large")` in
    `backend/src/inkstave/services/file_service.py`.
- Exception handlers in
  `/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/exception_handlers.py`:
  `app_error_handler` (AppError → envelope), `validation_error_handler`
  (`RequestValidationError` → 422 envelope with `details`), `unhandled_error_handler`
  (any other exception → 500 envelope, **never leaks internals**). Each injects a
  `request_id`.
- History diff route in
  `/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/api/routes/history.py`
  (`get_history_diff`, lines ~106–126): when `result.too_large` is true it returns
  `JSONResponse(result.model_dump(by_alias=True), status_code=413)`. The body is
  the **full diff shape** `{from, to, binary, too_large, hunks}` — NOT an error
  envelope. This asymmetry is intentional and must be preserved (it is what the
  client maps on).

If, while writing the 500-case test, you find no existing always-throwing test
route, add a **test-only** route registered solely inside the test (e.g. via the
`app` fixture / a router added in the test module) rather than shipping a
throwing endpoint in production code.

### 5.3 Frontend / UI (if any)

**The one code fix.** File:
`/home/inacio/Área de trabalho/code/inkstave/frontend/src/features/history/api.ts`,
function `getDiff` (lines ~79–99).

Today it calls `apiClient.get<…>()`, which routes through `request → requestRaw`
in `/home/inacio/Área de trabalho/code/inkstave/frontend/src/lib/api-client.ts`
and throws `await toApiError(res)` on `!res.ok` (line 142). A 413 therefore
throws an `ApiError` and the `too_large` body is discarded.

Requirement: `getDiff` must treat HTTP 413 as the "too large" signal and return a
structured result instead of propagating the throw. Implement with the **simplest**
option that does not change `api-client.ts`'s general contract:

- Wrap the `apiClient.get` call in `getDiff` in a `try/catch`; if the caught
  error is an `ApiError` (import `ApiError` from `@/lib/api-client`) with
  `status === 413`, return a synthesized `DiffResult`:
  `{ from, to, binary: false, tooLarge: true, hunks: [] }` (using the `from`/`to`
  arguments passed to `getDiff`). Re-throw any other error unchanged.

This keeps `api-client.ts` generic (still throws on `!res.ok`) and localizes the
413 semantics to the one caller that defines them. The existing
`HistoryDiffView` already renders the `tooLarge` branch
(`/home/inacio/Área de trabalho/code/inkstave/frontend/src/features/history/HistoryDiffView.tsx`
line ~92: "This version is too large to diff."), so no UI change is required —
the branch simply becomes reachable.

States already present in `HistoryDiffView` (do not duplicate): select-prompt,
loading skeleton, error+Retry (`role="alert"`), binary fallback, too-large
fallback, no-changes, and the rendered hunks. The loading/empty/error audit of
other views is **spec 64**, not here.

### 5.4 Real-time / jobs / external integrations (if any)

None.

### 5.5 Configuration

No new env vars. The relevant existing knob is `history_diff_max_bytes`
(default `2_097_152`) in
`/home/inacio/Área de trabalho/code/inkstave/backend/src/inkstave/config.py`;
backend tests may set it to a tiny value to force the `too_large` path.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently.

- `services/web/frontend/js/infrastructure/fetch-json.js` — how Overleaf's fetch
  wrapper distinguishes HTTP error statuses and attaches the parsed body to the
  thrown error (informs the "read the body even on a non-2xx" idea).
- `services/web/app/src/infrastructure/Errors.js` and the Express error
  middleware — how a uniform error response is shaped; learn the pattern only.
- Inkstave's history-diff "413 carries a structured body" pattern has **no direct
  Overleaf equivalent**; build it from this spec.

## 7. Acceptance criteria

1. **Given** the diff endpoint responds `200` with a normal diff body, **when**
   `getDiff` is called, **then** it returns the mapped `DiffResult`
   (`tooLarge: false`) exactly as today (no regression).
2. **Given** the diff endpoint responds `413` with body
   `{from, to, binary:false, too_large:true, hunks:[]}`, **when** `getDiff` is
   called, **then** it resolves (does **not** throw) to a `DiffResult` with
   `tooLarge === true`, `binary === false`, `hunks.length === 0`, and the same
   `from`/`to` that were requested.
3. **Given** the diff endpoint responds with a non-413 error (e.g. `403` or
   `500`), **when** `getDiff` is called, **then** it still **throws** an
   `ApiError` (the 413 handling must not swallow other errors).
4. **Given** the fixed `getDiff`, **when** `HistoryDiffView` renders against a
   413 diff, **then** it shows "This version is too large to diff." and **not**
   "Couldn't load the diff.".
5. **Given** the reconstructed document text exceeds `history_diff_max_bytes`,
   **when** the diff route is called, **then** the HTTP status is `413` and the
   JSON body contains `too_large: true` with the full diff shape (not an error
   envelope).
6. **Given** representative failing requests, **when** the backend responds for
   `401`/`403`/`404`/`409`/`413`(service errors)/`422`/`500`, **then** the body
   matches the `ErrorEnvelope` shape `{ error: { type, message, details?,
   request_id? } }` (the 413 *diff* case is the documented exception in AC5).
7. **Given** the `500` case, **when** the handler responds, **then** the body
   carries a generic message and **does not** leak the internal exception text or
   a stack trace.
8. **Given** a fetch that rejects (simulated network/timeout failure), **when**
   an `apiClient` call is made, **then** the rejection propagates as a catchable
   error (the caller can `try/catch`), with no unhandled rejection in the test.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Unit (Vitest):**
  - In `frontend/src/features/history/api.test.ts` (new): mock the global
    `fetch` (or mock `@/lib/api-client`) and assert AC1–AC3. For the 413 case,
    return a `Response` with status `413` and the real body shape and assert the
    resolved `DiffResult.tooLarge === true`. For a non-413 error, assert it
    throws `ApiError`. Follow the existing fetch-stub pattern in
    `frontend/src/lib/api-client.test.ts` (`vi.stubGlobal("fetch", …)`,
    `mockResponse(status, body)`).
  - In `frontend/src/features/history/HistoryDiffView.test.tsx` (extend): add a
    case wiring the real (fixed) `getDiff` mapping — or mock `getDiff` to resolve
    `tooLarge:true` (mirrors the existing "shows the too-large fallback" test) —
    and assert the "too large" copy appears and "Couldn't load the diff." does
    not. Use `renderWithProviders` from `frontend/src/test/utils.tsx`.
  - In `frontend/src/lib/api-client.test.ts` (extend): add a test where `fetch`
    rejects (`vi.fn().mockRejectedValue(new Error("timeout"))`) and assert the
    `apiClient.get(...)` promise rejects and is catchable (AC8).
- **Integration (pytest + httpx / test DB / fake Redis):**
  - In `backend/tests/integration/test_error_envelope_runtime.py` (new): using
    the `async_client`, `db_session`, `redis`, `app` fixtures from
    `backend/tests/conftest.py`, drive representative endpoints to produce
    `401`/`403`/`404`/`409`/`422` and assert each body matches `ErrorEnvelope`
    (`error.type`, `error.message`, and `request_id` present). For `500`, add a
    test-only throwing route to the `app` fixture inside the test and assert a
    generic 500 envelope with no leaked internals (AC6, AC7).
  - In `backend/tests/integration/test_history_api.py` (extend) or a focused new
    module: assert the diff route returns HTTP `413` with `too_large: true` (full
    diff shape) when `history_diff_max_bytes` is set tiny (AC5). Reuse the `hist`
    fixture pattern already in `test_history_api.py`.
- **E2E (Playwright):** none for this spec (fast tier only).
- **Performance/budget note:** All tests are pure-Python/JS with mocked fetch and
  the in-process ASGI client and fakeredis — no real network, no real diff of
  multi-MB content (the 413 path is forced via the tiny `history_diff_max_bytes`
  setting). No measurable addition to the 2-minute budget.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (the `getDiff` 413 mapping; verification
      tests for envelope, diff 413, and timeout).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes (measure with `just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, `mypy`, ESLint/Prettier, `tsc`).
- [ ] No new env vars; docs updated only if a decision note is added under `docs/`.
- [ ] No Overleaf code copied.
