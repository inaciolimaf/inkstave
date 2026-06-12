# Spec 90 — Fix-pack: backend/frontend test & interface gaps (batch 13) (requirements)

## 1. Summary

This fix-pack bundles nine validation-confirmed issues whose files are disjoint
from every other fix-pack, so it can run in parallel. The issues are almost all
**test-coverage / documentation** gaps inherited from specs 19, 26, 44, 46, 58
and 60: the agent SSE, cancel, and list-sessions HTTP endpoints are never
exercised through the test client; there is no event-protocol forward-compat unit
test; the docs README-links and deliverable-existence guards are too weak to
catch removed links or deleted files; the synctex non-member acceptance criterion
says 403 but the implementation deliberately returns 404 (documentation fix);
the agent transcript autoscroll/"jump to latest" behaviour is untested; and the
document-autosave feature lacks an HTTP-layer integration test the
spec requires. Only one change touches non-test source (`synctex/router.py`,
comment/doc-only — see issue 95).

## 2. Files in scope

Edit **only** these files (the payload set). Do not touch anything outside this
list; other fix-packs run concurrently on other files.

- `backend/src/inkstave/synctex/router.py`
- `backend/tests/integration/test_agent_api.py`
- `backend/tests/integration/test_synctex_api.py`
- `backend/tests/unit/test_agent_events.py`
- `backend/tests/unit/test_docs.py`
- `frontend/src/features/agent/AgentPanel.test.tsx`
- `frontend/src/features/agent/transcript.test.tsx`
- `frontend/src/features/editor/autosave/use-document-autosave.test.ts`

Restrict-edits note: prefer making each fix with the **fewest** files. Issue 67
(autosave HTTP-layer integration test) is covered with the existing
`vi.stubGlobal('fetch', ...)` harness — it does **not** add MSW and does **not**
edit `frontend/package.json` or the lockfile (those belong to other packs). If the
new test needs a sibling test file, keep it inside
`frontend/src/features/editor/autosave/` and treat it as part of this fix's
footprint; do not modify unrelated shared test setup.

## 3. Issues to fix

### Issue 176 — Agent SSE HTTP endpoint not tested via httpx streaming

- **ID:** 176
- **Source spec:** 44-agent-api-streaming
- **Severity:** minor (adjusted: minor)
- **File(s):** `backend/tests/integration/test_agent_api.py`,
  `backend/tests/unit/test_agent_events.py`
- **Problem:** Spec 44 §8 requires "SSE endpoint: subscribe via httpx streaming,
  assert the event sequence and terminal close." The
  `GET .../runs/{run_id}/events` HTTP endpoint is never called through the test
  client. `test_agent_api.py:131` only checks the `stream_url` **value** and
  never GETs it; the only SSE tests
  (`test_sse_forwards_live_events_then_closes`,
  `test_sse_replays_terminal_for_late_subscriber` in `test_agent_events.py`) call
  `sse_stream()` directly, bypassing the FastAPI route, the query-param token
  auth (`_sse_user`), and the project-membership check.
- **Fix to apply:** Add an integration test in `test_agent_api.py` that **GETs**
  `.../runs/{run_id}/events` through the async test client using httpx streaming,
  passing the JWT via the **query param** (the SSE auth path), and asserts the
  expected event sequence plus the terminal close. Drive events using the same
  scripted/stubbed agent mechanism the existing agent tests use (no real LLM).
  Keep the existing direct `sse_stream()` unit tests in `test_agent_events.py` as
  they are (they cover the function level); the new test covers the route + auth +
  membership wiring.

### Issue 177 — Agent cancel HTTP endpoint not tested

- **ID:** 177
- **Source spec:** 44-agent-api-streaming
- **Severity:** minor (adjusted: minor)
- **File(s):** `backend/tests/integration/test_agent_api.py`
- **Problem:** The `POST .../runs/{run_id}/cancel` HTTP endpoint (§5.2.6) is
  never exercised via the test client. AC6 (cancellation) is verified only at the
  job level: `test_agent_api.py:248` calls `request_cancel(redis, run_id, ...)`
  directly, skipping the HTTP route, its auth, and its run-state update logic.
- **Fix to apply:** Add an integration test in `test_agent_api.py` that **POSTs**
  to `.../runs/{run_id}/cancel` through the async test client and asserts: the
  authenticated member receives the expected 2xx response; the run transitions to
  **cancelled** (assert via the run state / `GET /sessions/{id}` or the run-state
  field the route updates); and (if cheap) a non-member / unauthenticated caller
  is rejected. Reuse existing fixtures for project/session/run creation.

### Issue 179 — Event-protocol forward-compat unit test missing

- **ID:** 179
- **Source spec:** 44-agent-api-streaming
- **Severity:** nit (adjusted: nit)
- **File(s):** `backend/tests/unit/test_agent_events.py`
- **Problem:** Spec 44 §8 lists "Event-protocol forward-compat (unknown type
  ignored by the test client)" as a required unit test. No such test exists
  (grep for forward/unknown/compat returns nothing).
- **Fix to apply:** Add a unit test in `test_agent_events.py` that feeds an event
  whose `type` is **unknown** (a forward-compatible/unrecognized event type) into
  the event parser/client used by the SSE machinery and asserts it is **ignored
  without error** (no exception; the unknown event does not break parsing of the
  surrounding known events). Use the same parsing/serialization helpers the
  existing unit tests use.

### Issue 178 — list_sessions HTTP endpoint not tested

- **ID:** 178
- **Source spec:** 44-agent-api-streaming
- **Severity:** minor (adjusted: minor)
- **File(s):** `backend/tests/integration/test_agent_api.py`
- **Problem:** Spec 44 §5.2.2 (`GET /sessions`, paginated list) has no HTTP-level
  test. Existing `agent/sessions` (no id) hits are all POSTs; the detail endpoint
  `GET /sessions/{id}` (§5.2.3) is exercised as a side-check
  (`test_agent_api.py:134`), but the **paginated list** endpoint is untested.
- **Fix to apply:** Add an integration test in `test_agent_api.py` that creates a
  couple of sessions and calls
  `GET /api/v1/projects/{project_id}/agent/sessions`, asserting: the paginated
  list payload (shape/pagination fields and that the created sessions appear);
  and member vs non-member authorization (a non-member is denied per the
  project-access pattern). Reuse existing session-creation helpers.

### Issue 245 — test_docs AC 7.10: README-links coverage gap

- **ID:** 245
- **Source spec:** 58-documentation
- **Severity:** minor (adjusted: minor)
- **File(s):** `backend/tests/unit/test_docs.py`
- **Problem:** The test for AC 7.10 (`docs/README.md` must link to every document
  in §5.1) only asserts a "Guides" heading exists (`test_docs.py:39`:
  `'docs/README.md': ['Guides']`). It does not assert that
  `user-guide.md`, `admin-guide.md`, `architecture.md`, `api-reference.md`, and
  `api/openapi.json` are actually linked. If a link were removed, the test would
  not catch it (`test_internal_links_resolve` only checks existing links aren't
  broken).
- **Fix to apply:** Add an assertion in `test_docs.py` that the **content** of
  `docs/README.md` contains a link to **each** §5.1 document path:
  `user-guide.md`, `admin-guide.md`, `architecture.md`, `api-reference.md`, and
  `api/openapi.json` (match by their relative paths as they appear in the README
  links). This must fail if any of those links is removed. Keep the existing
  "Guides" heading assertion.

### Issue 254 — No test guards existence of originality-audit.md / release-checklist.md

- **ID:** 254
- **Source spec:** 60-refactor-final
- **Severity:** minor (adjusted: minor)
- **File(s):** `backend/tests/unit/test_docs.py`
- **Problem:** No automated test asserts that `docs/originality-audit.md` and
  `docs/release-checklist.md` exist. The `_REQUIRED_SECTIONS` dict
  (`test_docs.py:22-72`) omits both, and `test_internal_links_resolve` iterates
  over files that happen to exist — a deleted file is silently skipped. DoD
  items 5 and 6 of spec 60 require these files; there is no regression guard.
- **Fix to apply:** Add `docs/originality-audit.md` and
  `docs/release-checklist.md` to the `_REQUIRED_SECTIONS` dict in
  `test_docs.py`, each with at least one required heading that actually exists in
  the file (read the current files to pick a stable heading). This makes the test
  fail if either file is deleted or loses its expected heading. Match the existing
  entry format used by the other required docs.

### Issue 95 — Synctex non-member status: AC says 403, impl returns 404

- **ID:** 95
- **Source spec:** 26-synctex
- **Severity:** major (adjusted: minor)
- **File(s):** `backend/src/inkstave/synctex/router.py`,
  `backend/tests/integration/test_synctex_api.py`
- **Problem:** Spec 26 criterion 8 requires both synctex endpoints to return
  **403** for a non-member. The implementation deliberately returns **404**
  (the Phase-2 `require_capability` anti-enumeration pattern), and
  `test_synctex_api.py:242-249` asserts 404 with a comment acknowledging the
  deviation. ADR 0026 documents the 404 choice as intentional, but the AC as
  written is unmet.
- **Fix to apply:** Apply the **documentation-level** resolution (preferred,
  given the deliberate anti-enumeration design — do **not** change the runtime
  status code, which would weaken the security posture):
  1. In `backend/src/inkstave/synctex/router.py`, ensure there is a clear comment
     (near `owned_project = require_capability(...)`) stating that non-members
     receive **404 (not 403)** by design — the Phase-2 anti-enumeration pattern,
     per ADR 0026 — explicitly noting this is a knowing deviation from spec 26
     criterion 8. (A `Non-member -> 404` comment already exists; extend it to
     reference the AC deviation and ADR 0026 so the intent is unambiguous.)
  2. In `backend/tests/integration/test_synctex_api.py`, keep the `== 404`
     assertion and make its comment explicitly cite the deliberate
     anti-enumeration design / ADR 0026 and the spec-26-criterion-8 deviation, so
     the test documents the intended behaviour rather than appearing to silently
     contradict the AC.
  Do **not** edit the spec-26 files or the ADR (out of scope); the documentation
  fix lives in the router comment and the test comment within this pack's scope.

### Issue 183 — Agent transcript autoscroll / "Jump to latest" untested

- **ID:** 183
- **Source spec:** 46-agent-chat-ui
- **Severity:** major (adjusted: major)
- **File(s):** `frontend/src/features/agent/transcript.test.tsx`,
  `frontend/src/features/agent/AgentPanel.test.tsx`
- **Problem:** The autoscroll unit test is entirely missing. Spec 46 §8 requires:
  "Autoscroll: pinned while at bottom; Jump to latest appears after scrolling up."
  No test covers this. The `AgentTranscript` component implements it (pinned
  state, "Jump to latest" affordance) but it is untested.
- **Fix to apply:** Add a Vitest+RTL test (preferably in `transcript.test.tsx`,
  the component-level file; use `AgentPanel.test.tsx` only if the behaviour is
  better exercised at the panel level) that:
  1. Renders the transcript scrolled to the **bottom**, adds new items, and
     asserts it stays **pinned** to the bottom (and the "Jump to latest"
     affordance is **not** shown).
  2. Simulates **scrolling up**, asserts the **"Jump to latest"** control
     appears; clicking it **re-pins** to the bottom (and the control disappears).
  Because jsdom does not implement real layout/scroll metrics, stub the necessary
  scroll properties (`scrollHeight`, `scrollTop`, `clientHeight`) and/or
  `scrollIntoView` as the component reads them, following any existing stubbing
  pattern in the agent tests. Keep it deterministic and fast.

### Issue 67 — Autosave: HTTP-layer integration test missing

- **ID:** 67
- **Source spec:** 19-document-autosave-rest
- **Severity:** major (adjusted: minor)
- **File(s):** `frontend/src/features/editor/autosave/use-document-autosave.test.ts`
- **Problem:** Spec 19 §8 requires an integration test that exercises the autosave
  flow at the HTTP boundary: type in the editor → the replace-content call is sent
  with body `{ content, version }` → status becomes Saved and the next save uses
  the new version; then a **409** response → the conflict flow resolves. The
  current `use-document-autosave.test.ts` mocks `saveDocument` at the function
  level (`vi.mock('../api', ...)`), bypassing the HTTP + API-client layer, so the
  request path/body/version handling is never verified.
- **Fix to apply:**
  1. Add an integration test for the autosave hook/flow that does **not**
     function-mock `saveDocument`. Mock at the **HTTP boundary** using the
     project's existing approach — `vi.stubGlobal('fetch', ...)` (the same
     fetch-stub harness already used elsewhere in the frontend tests) — so the
     real API-client code path runs. Do **not** introduce MSW or any new
     dependency, and do **not** edit `frontend/package.json` or the lockfile (MSW
     is intentionally avoided to keep this pack file-disjoint; the existing
     fetch-stub covers the HTTP layer).
  2. Assert: the request **path** is the correct replace-content endpoint; the
     request **body** is `{ content, version }` with the right values; on success
     the status becomes **Saved** and the **next** save uses the **new version**.
  3. Add a case where the stubbed `fetch` returns **409** and assert the
     **conflict flow resolves** as specified.
  Place the new test alongside the existing one (same directory). Keep the
  existing function-level unit test (it still covers the conflict logic at unit
  level); the new test adds the HTTP/body/path verification tier. Keep the
  fetch-stub setup/teardown local to this test file and keep it fast.

## 4. Acceptance criteria

1. **(176)** `test_agent_api.py` GETs `.../runs/{run_id}/events` via httpx
   streaming with a query-param token and asserts the event sequence and terminal
   close at the route level (auth + membership exercised).
2. **(177)** `test_agent_api.py` POSTs to `.../runs/{run_id}/cancel` via the test
   client and asserts the 2xx/auth behaviour and that the run transitions to
   cancelled.
3. **(178)** `test_agent_api.py` calls `GET .../agent/sessions` (paginated list)
   and asserts the list payload plus member/non-member authorization.
4. **(179)** `test_agent_events.py` has a unit test feeding an unknown event
   `type` and asserting it is ignored without error.
5. **(245)** `test_docs.py` asserts `docs/README.md` links to each §5.1 document
   (`user-guide.md`, `admin-guide.md`, `architecture.md`, `api-reference.md`,
   `api/openapi.json`) and fails if any link is removed.
6. **(254)** `test_docs.py` includes `docs/originality-audit.md` and
   `docs/release-checklist.md` in `_REQUIRED_SECTIONS` (with a real required
   heading each) so their absence fails the test.
7. **(95)** `synctex/router.py` documents the deliberate non-member **404**
   (anti-enumeration, ADR 0026, deviation from spec 26 criterion 8), and
   `test_synctex_api.py`'s `== 404` assertion comment cites this intent; the
   runtime status code is unchanged.
8. **(183)** A transcript autoscroll test asserts pinned-at-bottom on new items
   and that "Jump to latest" appears after scrolling up and re-pins on click.
9. **(67)** A fetch-stubbed integration test asserts the autosave PUT path and body
   `{ content, version }`, the Saved status, version advancement, and the 409
   conflict-resolution flow, without function-mocking `saveDocument` and without
   adding any dependency or editing `frontend/package.json`.
10. The full test suite passes (backend pytest + frontend Vitest) and stays under
    the 2-minute budget; lint/format/type-check remain clean.

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Slow work (real LLM, real Tectonic, real network) must stay stubbed.

- **Existing green:** Run the backend pytest and frontend Vitest suites first to
  confirm a green baseline. After fixes, re-run; nothing previously green may
  regress.
- **New / updated tests:**
  - **(176)** Integration: httpx-streamed GET of the SSE events route (query-param
    auth), event sequence + terminal close.
  - **(177)** Integration: POST cancel route → 2xx + run cancelled; auth checked.
  - **(178)** Integration: GET sessions list → payload + authz.
  - **(179)** Unit: unknown event type ignored without error.
  - **(245)** Unit (docs): README links to every §5.1 doc.
  - **(254)** Unit (docs): originality-audit.md and release-checklist.md required
    in `_REQUIRED_SECTIONS`.
  - **(183)** Vitest+RTL: transcript autoscroll pinned/jump-to-latest behaviour
    (with scroll metrics stubbed).
  - **(67)** Vitest+RTL with `vi.stubGlobal('fetch', ...)`: autosave PUT
    path/body, Saved + version advance, 409 conflict resolution (no MSW).
  - **(95)** No new runtime test; the existing synctex non-member test keeps its
    `== 404` assertion with a clarified, intent-documenting comment.
- **Performance/budget note:** All backend additions reuse scripted/stubbed agent
  and DB fixtures (no real LLM). The autosave test stubs `fetch` in-process (no
  network). Scroll-metric stubbing keeps the transcript test deterministic and
  instant. Keep added cases minimal to preserve the suite budget.

## 6. Definition of Done

- [ ] All issues in §3 (176, 177, 178, 179, 245, 254, 95, 183, 67) fixed exactly
      as described.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 are written and green; no previously green test
      regresses.
- [ ] The autosave integration test passes using the `fetch` stub, without
      function-mocking `saveDocument` and without any new dependency.
- [ ] Full test suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff for backend touched files; ESLint +
      Prettier + tsc for frontend touched files).
- [ ] Only files listed in §2 were edited (parallel-safe).
- [ ] No Overleaf code copied.
