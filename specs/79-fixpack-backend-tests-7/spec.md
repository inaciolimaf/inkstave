# Spec 79 — Fix-pack: backend/e2e test-coverage gaps + collab/ws nit (batch 7) (requirements)

## 1. Summary

This fix-pack remediates **9 confirmed issues** — all from validation review of
already-implemented specs — whose files are disjoint from every other fix-pack.
Most are **missing-test-coverage** gaps mandated by the source specs' acceptance
criteria and test plans (two absent Playwright e2e specs, several unit/integration
assertions). Two are small deviations: a collab/ws handshake that sends the
server's SyncStep1 twice, and the agent panel's resizability.

**Fixes:** 9 issues across 7 files/paths.

**Severity breakdown:** 0 major · 5 minor · 4 nit. *(The two e2e gaps — 122 and 55
— were initially flagged major; reviewers adjusted them to major/minor as
DoD-coverage gaps, not runtime bugs. Treat both as must-fix coverage items.)*

| ID  | Source spec | Severity | Area |
|-----|-------------|----------|------|
| 38  | 13-document-content-api | minor | `base_version > current` → 409 untested |
| 39  | 13-document-content-api | minor | `file` entity → 409 not_a_document (AC6) |
| 37  | 13-document-content-api | minor | replace_content version logic as **unit** tests |
| 122 | 32-presence-awareness-ui | major | missing Playwright two-context presence e2e |
| 55  | 17-file-tree-ui | minor | missing Playwright file-tree flow e2e |
| 24  | 08-auth-guards-sessions | nit | non-Bearer scheme → 401 untested |
| 99  | 27-compile-error-annotations | minor | font/class warning parser rules untested |
| 188 | 46-agent-chat-ui | nit | AgentPanel resizable (spec §5.4) |
| 112 | 29-collab-websocket | nit | duplicate server SyncStep1 at handshake |

## 2. Files in scope

Edit **only** these files/paths:

- `backend/src/inkstave/collab/ws/router.py`
- `backend/tests/integration/test_document_service.py`
- `backend/tests/integration/test_documents_api.py`
- `backend/tests/unit/test_guards.py`
- `backend/tests/unit/test_logparse_parser.py`
- `frontend/e2e/` *(add new Playwright spec files here: `presence.spec.ts` and a
  file-tree flow spec such as `file-tree.spec.ts`; reuse existing helpers in
  `frontend/e2e/support/` and patterns from existing specs)*
- `frontend/src/features/agent/AgentPanel.tsx`

For issue 37 the spec calls for **no-DB unit tests under `tests/unit/`**, but the
payload's in-scope files list `tests/integration/test_document_service.py` (not a
`tests/unit/` file). Resolve this by adding the pure version-logic unit tests as a
**new test module** is out of scope; instead add the no-DB assertions inside an
existing in-scope file — see issue 37 below for the exact approach that stays in
scope.

**Restrict edits to the files above.** Do not modify production source other than
`router.py` (issue 112) and `AgentPanel.tsx` (issue 188). All other edits are
tests/e2e only.

## 3. Issues to fix

### Issue 38 — `base_version > current version` must yield 409 (untested)
- **Source spec:** 13-document-content-api · **Severity:** minor
- **Files:** `backend/tests/integration/test_document_service.py`,
  `backend/tests/integration/test_documents_api.py`
- **Problem:** Spec 13 §5.2 says "If `base_version > current version` (impossible
  normally): also 409." No test passes a `base_version` greater than the current
  version. Existing tests use only `base_version` 0 and 1.
- **Fix to apply:** Add a service-layer test (in `test_document_service.py`) and an
  API test (in `test_documents_api.py`) that write content with `base_version=5`
  against a document at version 0/1 and assert a **409 version_conflict** (the
  `WHERE version=base_version` update matches 0 rows). Reuse the existing fixtures
  and the same conflict-assertion style as the existing stale-version tests.

### Issue 39 — `file` entity → 409 not_a_document (AC6)
- **Source spec:** 13-document-content-api · **Severity:** minor
- **Files:** `backend/tests/integration/test_documents_api.py`,
  `backend/tests/integration/test_document_service.py`
- **Problem:** AC6: "Given a `folder` **or `file`** entity id, when GET/PUT content
  on it, then 409 not_a_document." Tests cover only `folder` entities
  (`test_not_a_document_for_folder`, API test line ~145); no test uses a
  `TreeEntityType.file` entity.
- **Fix to apply:** Add parallel tests creating a **`file`** entity (the same way
  the folder tests create a folder, e.g. `_entity(..., 'file', ...)` /
  `TreeEntityType.file`) and assert GET and PUT content both return **409
  not_a_document** — at both the service layer (`test_document_service.py`) and via
  the API (`test_documents_api.py`).

### Issue 37 — replace_content version logic as no-DB unit tests
- **Source spec:** 13-document-content-api · **Severity:** minor
- **File:** `backend/tests/integration/test_document_service.py`
- **Problem:** Spec 13 §8 (lines 237–241) lists, under **Unit (pytest)**:
  `replace_content` version logic (equal/greater/less `base_version`), `size_bytes`
  multibyte recomputation, `ensure_document` idempotency, and `NotADocument` for
  folder/file. These were all written as DB integration tests; no `tests/unit/`
  file references `document_service`.
- **Fix to apply:** Add the pure, no-DB portions of this logic as fast assertions
  **without requiring Postgres**. Specifically:
  - For `size_bytes` multibyte recomputation: assert the helper/logic that computes
    byte length counts multibyte characters correctly (e.g. a string with accented
    / non-ASCII / multibyte characters yields the expected UTF-8 byte count), as a
    pure function call with no DB.
  - For the version-branch decision (equal vs greater vs less `base_version`):
    assert the pure conditional outcome (write accepted only when
    `base_version == current`; otherwise conflict) at whatever pure level the code
    exposes.
  Place these no-DB assertions in a clearly-marked unit-style section/test function
  within `test_document_service.py` (the in-scope file) that does **not** use the
  DB fixture, so they run as pure logic. (Staying inside the in-scope file is
  required; do not create a new `tests/unit/` module.) Keep the existing
  integration tests for the DB-backed branches.

### Issue 122 — Missing Playwright two-context presence e2e (major)
- **Source spec:** 32-presence-awareness-ui · **Severity:** major
- **Path:** `frontend/e2e/`
- **Problem:** Spec 32 §8 and DoD §9 require **exactly one** Playwright two-context
  e2e test: moving the cursor / making a selection in context A renders a labelled
  remote cursor and an avatar in context B. ADR 0032 names it
  `e2e/presence.spec.ts`. The file does not exist; `collab.spec.ts` explicitly
  skips presence rendering and defers to Vitest.
- **Fix to apply:** Create `frontend/e2e/presence.spec.ts` with **two browser
  contexts** opening the same document. In context A move the cursor / make a
  selection; in context B assert that a **labelled remote cursor** and a remote
  **avatar** for the other user render. Reuse the existing e2e harness/helpers
  (`frontend/e2e/support/`, `global-setup.ts`, the patterns used by
  `collab.spec.ts`). Keep it to one test and within the suite budget (use the
  existing seeded project / auth helpers; await presence with sensible timeouts).

### Issue 55 — Missing Playwright file-tree flow e2e
- **Source spec:** 17-file-tree-ui · **Severity:** minor
- **Path:** `frontend/e2e/`
- **Problem:** Spec 17 §8 requires **exactly one** Playwright spec covering the
  full file-tree flow: open seeded project → create folder → create doc inside it →
  rename the doc → drag it to root → upload a small binary file → delete the
  folder. No such file exists (`editor.spec.ts` only creates+opens a file).
- **Fix to apply:** Create `frontend/e2e/file-tree.spec.ts` (or similar) exercising
  the full flow against the seeded project: create a folder, create a doc inside
  it, rename the doc, drag it to root, upload a small binary file, and delete the
  folder — asserting the tree state after each step. Reuse existing e2e helpers
  (`createFile`/`openFile` and friends in `support/`) and auth/seed setup. Keep it
  one spec; use a tiny in-memory binary for the upload so it stays fast.

### Issue 24 — Non-Bearer scheme → 401 (untested)
- **Source spec:** 08-auth-guards-sessions · **Severity:** nit
- **File:** `backend/tests/unit/test_guards.py`
- **Problem:** Spec §8 unit plan lists "Header parsing: missing, **non-Bearer**,
  empty token → mapped to 401 error". Tests exist for missing credentials and
  empty token, but not for a non-Bearer scheme (e.g. `Authorization: Basic xxx`).
- **Fix to apply:** Add a unit test simulating a non-Bearer scheme. Since
  `HTTPBearer(auto_error=False)` returns `None` for a non-Bearer Authorization
  header, pass `HTTPAuthorizationCredentials(scheme="Basic", credentials="xxx")`
  (or simulate the dependency receiving `None` for a non-Bearer header) into
  `get_current_user` and assert it raises a **401**. Match the style of
  `test_get_current_user_without_credentials_raises_401`.

### Issue 99 — Font/Class warning parser rules untested
- **Source spec:** 27-compile-error-annotations · **Severity:** minor
- **File:** `backend/tests/unit/test_logparse_parser.py`
- **Problem:** Spec §8 (line 279) requires "each warning class" be covered. The
  parser handles `font-warning` and `class-warning` rules
  (`latex_log_parser.py` lines ~137–140) but no test exercises them; existing tests
  cover latex-warning, package-warning, undefined-citation only.
- **Fix to apply:** Add unit tests feeding representative log lines for
  **`LaTeX Font Warning:`** and **`Class <x> Warning:`** into the parser and
  asserting the produced annotation's **exact rule id** (`font-warning` /
  `class-warning`) and **severity** (warning). Mirror the structure of the existing
  warning-class tests.

### Issue 188 — AgentPanel must be resizable (spec §5.4)
- **Source spec:** 46-agent-chat-ui · **Severity:** nit
- **File:** `frontend/src/features/agent/AgentPanel.tsx`
- **Problem:** Spec 46 §5.4 says the AgentPanel is "Resizable/collapsible; open/
  closed state persisted". The panel is a fixed-width shadcn `Sheet`
  (`className="sm:max-w-md"`, lines ~87–166) — collapsible but not user-resizable.
- **Fix to apply:** Make the panel user-resizable. Either (a) wrap/replace the
  fixed-width Sheet content with a resizable container using the approved stack's
  resizable primitive (e.g. shadcn `ResizablePanelGroup`/`ResizablePanel` backed by
  `react-resizable-panels`, if already present), or (b) allow a draggable width
  handle that persists the chosen width alongside the existing open/closed
  persistence. Preserve the existing collapsible behaviour and persisted open/closed
  state. Do not regress existing AgentPanel tests; if no resizable primitive exists
  in the project and adding one is out of scope, implement a minimal CSS
  drag-to-resize handle on the panel edge that persists width. Keep within the
  approved stack — no new heavy dependency beyond what shadcn/ui already provides.

### Issue 112 — Duplicate server SyncStep1 at handshake
- **Source spec:** 29-collab-websocket · **Severity:** nit
- **File:** `backend/src/inkstave/collab/ws/router.py`
- **Problem:** Spec 29 §5.2.1 receive-loop notes: on a client SyncStep1, send step2
  then "(if not already) `encode_sync_step1(...)`". The server already enqueues its
  step1 at handshake time (line ~302). When the client sends its own step1,
  `_dispatch` (lines ~157–162) unconditionally re-enqueues `server_step1`, so the
  server's step1 is sent **twice** per handshake. Yjs treats duplicate step1 as
  idempotent (no correctness bug), but it wastes a frame and ignores the spec's "if
  not already" guard.
- **Fix to apply:** Track a per-connection flag indicating the server's step1 was
  already sent at handshake time (set when enqueuing it at line ~302). In
  `_dispatch`, when handling a client SyncStep1, still send `step2`, but only
  enqueue `server_step1` if the flag is unset; otherwise skip the duplicate. (Clear
  semantics: the server sends its own step1 exactly once per connection.) Keep all
  existing collab/ws tests green.

## 4. Acceptance criteria

1. A test writes content with `base_version=5` against a v0/v1 document and asserts
   409 version_conflict — at both the service layer and the API (issue 38).
2. Tests create a `file` entity and assert GET and PUT content return 409
   not_a_document — at both the service layer and the API (issue 39).
3. `test_document_service.py` contains no-DB assertions for `size_bytes` multibyte
   byte-count recomputation and the version-branch decision logic, runnable without
   Postgres (issue 37).
4. `frontend/e2e/presence.spec.ts` exists: two browser contexts, context-A cursor
   move renders a labelled remote cursor and avatar in context B (issue 122).
5. A Playwright file-tree e2e spec exists covering create folder → create doc →
   rename → drag to root → upload small binary → delete folder (issue 55).
6. `test_guards.py` has a test asserting a non-Bearer Authorization scheme maps to
   401 (issue 24).
7. `test_logparse_parser.py` has tests asserting `font-warning` and `class-warning`
   rule ids and warning severity from representative log lines (issue 99).
8. `AgentPanel.tsx` renders a user-resizable panel while preserving collapsible +
   persisted open/closed state (issue 188).
9. `router.py` sends the server's SyncStep1 exactly once per connection (guarded by
   a per-connection flag); a client SyncStep1 still gets a step2 (issue 112).
10. The full suite (pytest + Vitest + the two new Playwright specs) stays green and
    under 2 minutes; only §2 files are modified.

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Slow work (LaTeX, real LLM, real compile) stays stubbed; e2e stays minimal.

- **Existing green:** Run `test_document_service.py`, `test_documents_api.py`,
  `test_guards.py`, `test_logparse_parser.py`, the collab/ws router tests, the
  AgentPanel Vitest tests, and the existing Playwright suite before changes to
  confirm baseline green.
- **New/updated tests:**
  - *Integration (pytest):* base_version>current 409 (38); file-entity 409 (39).
  - *Unit (pytest, no DB):* size_bytes/version-branch pure assertions (37);
    non-Bearer 401 (24); font/class warning rules (99).
  - *E2E (Playwright):* `presence.spec.ts` two-context presence (122);
    `file-tree.spec.ts` full file-tree flow (55) — both reusing existing
    harness/helpers and the seeded project.
  - *Frontend unit (Vitest):* keep AgentPanel tests green after the resizable
    change (188); add an assertion for the resize handle if a stable selector
    exists.
  - *Backend:* keep collab/ws router tests green; assert (if a test hook exists)
    that exactly one server step1 is sent per handshake (112).
- **Run:**
  - `pytest backend/tests/integration/test_document_service.py backend/tests/integration/test_documents_api.py backend/tests/unit/test_guards.py backend/tests/unit/test_logparse_parser.py`
  - `pytest backend/tests -k collab or ws` (router tests)
  - `npm --prefix frontend run test -- AgentPanel`
  - `npm --prefix frontend run e2e -- presence file-tree` (or the project's e2e runner)
- **Performance/budget note:** The two new e2e specs are single, focused flows on
  the already-seeded project; pytest additions are fast (no-DB unit + reuse of
  existing fixtures). Keep e2e timeouts tight to protect the 2-minute budget.

## 6. Definition of Done

- [ ] All 9 issues (38, 39, 37, 122, 55, 24, 99, 188, 112) fixed exactly as in §3.
- [ ] All acceptance criteria in §4 pass.
- [ ] Only the seven files/paths in §2 are modified (new e2e specs live under
      `frontend/e2e/`).
- [ ] `router.py` and `AgentPanel.tsx` are the only production source files changed.
- [ ] Affected pytest, Vitest, and the two new Playwright specs are green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] No Overleaf code copied.
