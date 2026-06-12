# Spec 70 — Fix-Pack: Backend & Frontend Tests #2 (requirements)

## 1. Summary

This fix-pack resolves **9 confirmed issues** found by a two-reviewer validation
pass across specs 02, 08, 24, 26, 27, 46, and 57. They cover: a missing
strict-mode migration-refusal unit test (`#240`), a missing integrated SyncTeX
inverse-sync component test (`#96`), a missing PDF zoom re-render assertion
(`#91`), a missing auth rate-limiter fail-open integration test (`#23`), a
frontend `ChatSession` type-contract divergence (`#185`), and four
deviation/placement notes for CORS, dead middleware, the SyncTeX guard test
location, and an API-client path (`#5`, `#4`, `#98`, `#103`).

**Severity breakdown (adjusted):**
- major: 2 (`#240`, `#96`)
- minor: 4 (`#5`, `#4`, `#91`, `#23`, `#185` — five minors counting `#185`)
- nit: 2 (`#98`, `#103`)

> `#5`, `#4`, `#98`, `#103` are **deviation / layout** findings whose correct
> resolution is a **documented note** (and, for `#185`, a small type fix), not a
> behaviour regression. Each says so explicitly below — do not revert working,
> stricter behaviour just to match an older spec's literal wording.

## 2. Files in scope

Edit **only** these files. They are disjoint from all other fix-packs.

```
backend/src/inkstave/app.py
backend/src/inkstave/middleware.py
backend/tests/integration/test_guards.py
backend/tests/integration/test_security_api.py
backend/tests/unit/test_bootstrap_57.py
backend/tests/unit/test_synctex_parser.py
backend/tests/unit/test_synctex_service.py
frontend/src/features/agent/types.ts
frontend/src/features/pdf-preview/PdfViewer.synctex.test.tsx
frontend/src/features/pdf-preview/PreviewPane.synctex.test.tsx
frontend/src/features/pdf-preview/problems.ts
```

**NOTE:** Restrict all edits to the paths above. Several issues reference source
files (e.g. `PdfViewer.tsx`, `account` services) as evidence — those are
**read-only references**; the fix lands in the in-scope test/type/doc files. If a
fix appears to require editing a file not on this list, stop and report.

## 3. Issues to fix

### 3.1 — `#240` Missing strict-mode startup-refusal unit test (major · spec 57)

- **Files:** `backend/tests/unit/test_bootstrap_57.py`,
  `backend/src/inkstave/app.py` (read-only reference)
- **Problem:** Spec 57 §8 / AC5 require a unit test proving that when
  `MIGRATE_ON_START=false` and the DB is **behind head**, the app **refuses to
  start** with a clear pending-migrations error. `test_bootstrap_57.py` (~lines
  132–136) only tests the `is_database_at_head` comparison logic; nothing exercises
  `_ensure_migrations` (app.py ~lines 54–62) raising `RuntimeError("Database is not
  at the latest migration…")` when `migrate_on_start=False` and the DB is not at
  head. The code is correct but untested.
- **Fix:** Add a unit test in `test_bootstrap_57.py` that mocks
  `is_database_at_head` to return `False`, sets `migrate_on_start=False` (via
  settings/monkeypatch following the existing test style), calls
  `_ensure_migrations`, and asserts it raises `RuntimeError` whose message contains
  "not at the latest migration" (match the actual message in app.py). No production
  code change.

### 3.2 — `#96` Missing integrated SyncTeX inverse-sync component test (major · spec 26)

- **Files:** `frontend/src/features/pdf-preview/PdfViewer.synctex.test.tsx`,
  `frontend/src/features/pdf-preview/PreviewPane.synctex.test.tsx`
- **Problem:** Spec 26 criterion 10 / §8 require a Vitest+RTL test that, with the
  synctex API **mocked**, demonstrates: clicking a PDF page calls the synctex
  (`pdfToCode`) API and the **editor then scrolls to the returned line with a
  highlight decoration**. Today `PdfViewer.synctex.test.tsx` tests `onPageClick`
  coordinates and overlay rendering as **two separate** tests with no API mock and
  no editor `revealLine`/scroll assertion; `PreviewPane.synctex.test.tsx` (~lines
  86–107) only covers forward sync (criterion 11).
- **Fix:** Add a component test (preferably in `PreviewPane.synctex.test.tsx`, where
  the editor and PDF viewer are integrated; otherwise in `PdfViewer.synctex.test.tsx`
  if that is where the wiring is testable) that:
  1. mocks the `pdfToCode` synctex API to resolve to a known target line;
  2. simulates a PDF page click (reuse the existing click-simulation helper that the
     coordinate test already uses);
  3. asserts the mocked `pdfToCode` was called with the click's PDF-point
     coordinates; and
  4. asserts the editor issues a scroll/`revealLine` to the returned line and shows
     a highlight decoration (assert on the spy/effect that the editor exposes for
     reveal+highlight, matching how the forward-sync test asserts behaviour).
  Keep the existing separate tests; this adds the missing end-to-end-of-the-feature
  inverse-sync test.

### 3.3 — `#91` Missing PDF zoom re-render assertion (minor · spec 24)

- **File:** `frontend/src/features/pdf-preview/PdfViewer.synctex.test.tsx`
- **Problem:** Spec 24 §8 requires the PDF.js wrapper test to assert the document is
  **re-rendered on zoom change**. The behaviour exists (`PdfPage` effect deps
  `[pdf, pageNumber, scale]`), but no test asserts that changing `scale` re-invokes
  `pdf.getPage` / `page.render`. There is no `PdfViewer.test.tsx`, and
  `usePdfDocument.test.ts` has no scale case.
- **Fix:** Add a test to `PdfViewer.synctex.test.tsx` (the in-scope PDF viewer test
  file) that, with `pdfjs-dist` mocked, mounts the viewer at one `scale`, then
  re-renders with a **different** `scale` prop, and asserts `getPage`/`render`
  (whichever the mock exposes) is invoked **again** for the new scale. Reuse the
  existing pdfjs mock setup in this file.

### 3.4 — `#23` Missing auth rate-limiter fail-open integration test (minor · spec 08)

- **Files:** `backend/tests/integration/test_guards.py`,
  `backend/tests/integration/test_security_api.py`
- **Problem:** Spec 08 AC8 / §8 require covering the rate-limiter **fail-open** path
  (Redis unavailable → request allowed, warning logged). It is covered at unit level
  (`test_rate_limit.py`) and at integration level only for `security.rate_limit`
  (`test_security_api.py`), but **not** for the **auth** rate-limiter over HTTP in
  `test_guards.py`.
- **Fix:** Add an integration test in `test_guards.py` that monkeypatches the Redis
  client used by the **auth** `rate_limit` so its calls raise (simulating Redis
  down), then `POST`s to the login route and asserts the request is **allowed**
  (i.e. not a 429 from the limiter; it proceeds to normal auth handling) — i.e. the
  limiter fails open. Optionally assert a warning is logged (using `caplog`),
  matching how the unit test (`test_rate_limit.py::test_limiter_fails_open_when_redis_errors`)
  asserts the warning. Follow the existing `test_guards.py` HTTP-client and
  monkeypatch patterns. (`test_security_api.py` is in scope for reference/symmetry;
  no change is required there unless you mirror the helper.)

### 3.5 — `#185` `ChatSession` type contract divergence (minor · spec 46)

- **File:** `frontend/src/features/agent/types.ts`
- **Problem:** The `ChatSession` interface (~lines 5–11) diverges from spec 46 §5.1:
  it adds a non-spec `runState: string` field and is **missing** the spec-required
  `updatedAt: string`. Spec contract: `{ id, projectId, title, createdAt, updatedAt }`.
- **Fix:** Add `updatedAt: string` to `ChatSession`. Remove `runState` from
  `ChatSession`; if `runState` is used by runtime code, move it to a separate
  runtime-state type (e.g. a `ChatSessionRuntimeState` interface or extend it
  locally where used) rather than polluting the server-contract type. Update any
  in-scope references so the frontend type-checks. Do **not** edit consumers outside
  the in-scope file — if removing `runState` would break an out-of-scope file, keep
  `runState` as an **optional** field (`runState?: string`) clearly commented as
  non-contract runtime state, and still add `updatedAt`. The required outcome is:
  `updatedAt` present; `runState` no longer part of the spec contract shape.

### 3.6 — `#5` CORS uses explicit method/header lists, not wildcards — DOC NOTE (minor · spec 02)

- **File:** `backend/src/inkstave/app.py`
- **Problem:** Spec 02 §5.2 specifies `allow_methods=["*"]`, `allow_headers=["*"]`,
  but `create_app()` (app.py ~lines 175–176) uses explicit lists
  (`["GET","POST","PUT","PATCH","DELETE","OPTIONS"]` and
  `["Authorization","Content-Type", settings.request_id_header]`). This is a
  stricter, arguably better policy, but it deviates from the spec text and no ADR
  records the tightening.
- **Fix (prefer keeping the stricter policy):** Do **not** loosen CORS back to
  wildcards. Add a short code comment at the CORS middleware setup in `app.py`
  explaining the deliberate tightening (explicit allow-lists for defense-in-depth)
  and noting it supersedes spec 02's literal `["*"]`. (Recording an ADR would be
  ideal, but ADR files are out of scope for this pack; the in-scope resolution is
  the explanatory comment in `app.py`.)

### 3.7 — `#4` Dead `middleware.py` `RequestIdMiddleware` — DOC NOTE / dead-code (minor · spec 02)

- **Files:** `backend/src/inkstave/middleware.py`,
  `backend/src/inkstave/app.py` (read-only reference)
- **Problem:** Spec 02 §5.2's module layout lists `middleware.py` with
  `RequestIdMiddleware`, but `create_app()` uses
  `observability.middleware.RequestContextMiddleware` instead (app.py ~lines
  32/181). `middleware.RequestIdMiddleware` is never imported by production code
  (`grep 'from inkstave.middleware import'` → 0 hits) — it is dead code.
  `RequestContextMiddleware` is functionally equivalent (same ContextVar request-id,
  header echo, access log).
- **Fix (prefer documenting + de-dead-coding without behaviour change):** Add a
  clear module-level docstring/comment at the top of `middleware.py` stating that
  the active request-id middleware is `observability.middleware.RequestContextMiddleware`
  and that `RequestIdMiddleware` here is retained only as the spec-02 reference
  implementation (or is deprecated). **Do not** rewire `create_app()` to swap
  middlewares (that risks behaviour changes and touches the observability path which
  is out of scope). The minimal, safe resolution is the explanatory note marking the
  class as superseded. (If the project prefers deleting dead code, deleting
  `RequestIdMiddleware` is acceptable **only** if nothing — including the
  `logging.py` docstring reference noted in evidence — imports it; verify with grep
  first, and since `logging.py` is out of scope, prefer the docstring/deprecation
  note over deletion.)

### 3.8 — `#98` SyncTeX `MAX_GZ_BYTES` guard test placement — DOC NOTE (nit · spec 26)

- **Files:** `backend/tests/unit/test_synctex_parser.py`,
  `backend/tests/unit/test_synctex_service.py`
- **Problem:** Spec 26 §8 places the `SYNCTEX_MAX_GZ_BYTES` guard test in the
  parser tests, but it actually lives in `test_synctex_service.py`
  (`test_oversize_synctex_is_refused`, ~lines 79–83) — architecturally correct,
  because the **service** enforces the guard before calling the parser. The parser
  tests don't cover the guard. No functionality is broken.
- **Fix:** Add a brief comment in `test_synctex_parser.py` (e.g. near where a
  size-guard test would otherwise be expected) explaining that the
  `SYNCTEX_MAX_GZ_BYTES` guard is enforced at the **service** layer and is therefore
  tested in `test_synctex_service.py::test_oversize_synctex_is_refused` (the
  architecturally correct location). No behaviour change.

### 3.9 — `#103` `problems.ts` API-client path deviation — DOC NOTE (nit · spec 27)

- **File:** `frontend/src/features/pdf-preview/problems.ts`
- **Problem:** Spec 27 §5.3 specifies the API client at
  `frontend/src/lib/api/problems.ts`, but it lives at
  `features/pdf-preview/problems.ts` — cohesively placed with its feature, but a
  literal layout deviation. `frontend/src/lib/api/problems.ts` does not exist.
- **Fix (prefer keeping the cohesive location):** Do **not** move the file (moving
  it would touch out-of-scope importers). Add a short top-of-file comment in
  `problems.ts` noting that spec 27 §5.3 nominally placed this client under
  `src/lib/api/`, but it is intentionally co-located with the `pdf-preview` feature
  it serves. No behaviour change.

## 4. Acceptance criteria

1. **`#240`** A unit test asserts `_ensure_migrations` raises `RuntimeError`
   (message contains "not at the latest migration") when `migrate_on_start=False`
   and `is_database_at_head` is mocked to `False`.
2. **`#96`** A component test mocks `pdfToCode`, simulates a PDF page click, asserts
   the API is called with the click coordinates, and asserts the editor scrolls/
   reveals the returned line with a highlight decoration.
3. **`#91`** A PDF viewer test asserts that changing `scale` re-invokes
   `getPage`/`render` (zoom re-render), with `pdfjs-dist` mocked.
4. **`#23`** An integration test makes the auth rate-limiter's Redis raise and
   asserts the login request is allowed (fail-open), not 429.
5. **`#185`** `ChatSession` includes `updatedAt: string`; `runState` is no longer
   part of the spec-contract shape (removed, or relocated/marked optional non-
   contract); frontend type-checks.
6. **`#5`** `app.py` has a comment explaining the deliberate CORS tightening over
   spec 02's wildcards; CORS policy unchanged (still explicit lists).
7. **`#4`** `middleware.py` documents that `RequestContextMiddleware` is the active
   request-id middleware and `RequestIdMiddleware` is superseded/retained as
   reference; `create_app()` unchanged.
8. **`#98`** `test_synctex_parser.py` notes the size guard is tested at the service
   layer (`test_oversize_synctex_is_refused`).
9. **`#103`** `problems.ts` notes its intentional feature-local placement vs spec 27
   §5.3.
10. Backend (pytest) and frontend (Vitest) suites are green; full suite **< 2
    minutes**.

## 5. Test plan

> Keep the combined suite under 2 minutes. Mock pdfjs / synctex API / Redis; no
> real LaTeX, network, or Redis.

- **Stay green:** All existing tests in `test_bootstrap_57.py`, `test_guards.py`,
  `test_security_api.py`, `test_synctex_parser.py`, `test_synctex_service.py`,
  `PdfViewer.synctex.test.tsx`, and `PreviewPane.synctex.test.tsx` must still pass.
- **New / updated tests proving each fix:**
  - `test_bootstrap_57.py`: strict-mode refusal test (`#240`).
  - `PreviewPane.synctex.test.tsx` (or `PdfViewer.synctex.test.tsx`): inverse-sync
    integrated test with mocked `pdfToCode` and editor reveal+highlight assertion
    (`#96`).
  - `PdfViewer.synctex.test.tsx`: zoom-change re-render assertion (`#91`).
  - `test_guards.py`: auth rate-limiter fail-open integration test (`#23`).
  - `frontend/src/features/agent/types.ts`: contract fix verified by the existing
    Vitest type-check / build (`#185`).
- **Performance/budget note:** All new tests are mocked/in-memory (mocked pdfjs,
  mocked synctex API, mocked/raising Redis, mocked Alembic head check). No real
  sleeps or I/O. Verify the budget with `just test-timed`.

## 6. Definition of Done

- [ ] All 9 issues in §3 fixed (behaviour/test fixes for `#240`, `#96`, `#91`,
      `#23`, `#185`; documented-note resolutions for `#5`, `#4`, `#98`, `#103`).
- [ ] All acceptance criteria in §4 pass.
- [ ] New/updated tests in §5 written and green (backend + frontend).
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`; ESLint/`tsc`).
- [ ] Edits limited to the files in §2 — no out-of-scope files touched.
- [ ] No Overleaf code copied; stack unchanged.
