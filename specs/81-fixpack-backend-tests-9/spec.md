# Spec 81 — Fix-pack: compile/logparse semantics & test gaps (batch 9) (requirements)

## 1. Summary

This fix-pack applies **9 confirmed issues** validated by two independent
reviewers. They span two genuine backend semantic/behavioural fixes (compile
log-excerpt slice direction; compile-job authorization), a spec-wording
reconciliation for logparse truncation, and several confirmed test-coverage gaps
(migration backfills, register happy-path, route-template extraction, dead test
fixture).

Severity breakdown (adjusted severity):
- **major:** 0
- **minor:** 6 (IDs 77, 78, 137, 131, 34, 27; ID 212 adjusted to minor)
- **nit:** 2 (IDs 102, 166)

(ID 212 was originally filed as major but adjusted to minor by review.)

Source specs touched: `09-frontend-foundation`, `12-file-tree-model`,
`22-compile-api-async-jobs`, `27-compile-error-annotations`,
`33-collaborators-sharing`, `34-access-control`, `41-agent-foundation`,
`51-observability`.

## 2. Files in scope

Edit **only** these files (exact payload set). Do not modify anything outside
this list — other fix-packs run in parallel on disjoint files.

- `backend/src/inkstave/compile/jobs.py`
- `backend/src/inkstave/logparse/service.py`
- `backend/tests/integration/test_migrations.py`
- `backend/tests/unit/test_agent_llm.py`
- `backend/tests/unit/test_observability.py`
- `frontend/src/pages/register.test.tsx`

> Restrict-edits note: Issue 102 and Issue 78 are partly about reconciling
> spec/ADR wording. Spec/ADR documents are **not** in this pack's file set, so
> for those issues apply the **code-side** change described in §3 (or, where the
> fix is purely documentation, record the chosen behaviour in a code comment in
> the in-scope source file). Do not edit files outside §2.

## 3. Issues to fix

### Issue 77 — compile `log_excerpt` stores the HEAD instead of the tail
- **Source spec:** 22-compile-api-async-jobs
- **Severity:** minor
- **File(s):** `backend/src/inkstave/compile/jobs.py`
- **Problem:** `jobs.py:188` does `log_excerpt=result.log_text[:2000] or None`,
  storing the **first** 2000 chars. Spec 22 §5.1 requires a "truncated **tail** of
  log_text for quick display." For LaTeX, errors appear at the end, so the head is
  the wrong slice. The existing `test_failure_records_log_excerpt` uses a short
  string that fits in both head and tail, masking the regression.
- **Fix to apply:** Change the slice to the tail: `result.log_text[-2000:] or None`.
  Add (or extend) a test with a **long** log (> 2000 chars) where the meaningful
  error text is at the end, and assert the stored `log_excerpt` contains that
  trailing error text (and not the leading filler). If the new test belongs in a
  compile-jobs test file outside §2, place the assertion in an in-scope test file
  only if one already covers this; otherwise keep the code fix and rely on existing
  in-scope test files — do **not** create new files outside §2. (The slice fix is
  the load-bearing change; cover it with the nearest existing in-scope test, e.g.
  extend coverage via `test_migrations.py` is **not** appropriate — only add the
  test if it naturally lives in an in-scope file. If no in-scope test file fits,
  apply the code fix and note the manual-verification rationale in the DoD.)

### Issue 78 — cancel watcher polls the flag, never subscribes to pub/sub
- **Source spec:** 22-compile-api-async-jobs
- **Severity:** minor
- **File(s):** `backend/src/inkstave/compile/jobs.py`
- **Problem:** `_cancel_watcher` (jobs.py:72-77) polls `is_cancel_requested` (a
  Redis key-exists check) on a 50ms sleep loop and never subscribes to the
  `compile:cancel:{compile_id}` pub/sub channel. `stream.py` publishes to that
  channel, but nothing in the worker subscribes. Spec 22 §5.4.2 says the watcher
  reacts to "the pub/sub message **or** flag." Functionally equivalent, but a
  stated-architecture deviation (already acknowledged by the ADR).
- **Fix to apply:** Choose the lower-risk option consistent with the existing ADR:
  record that flag-polling is the chosen cancel mechanism. Since spec/ADR files are
  out of scope here, add a clarifying code comment in `_cancel_watcher` documenting
  that the watcher intentionally polls the cancel **flag** (set alongside the
  pub/sub publish in `stream.py`) and that pub/sub subscription is deliberately not
  used in the worker. Do not remove the existing flag-polling behaviour. (If the
  implementer prefers the architecture-faithful option — adding a pub/sub
  subscription — that is acceptable **only** if confined to `jobs.py`; otherwise
  prefer the comment-documenting approach.)

### Issue 137 — compile ARQ job performs no membership/COMPILE check
- **Source spec:** 34-access-control
- **Severity:** minor
- **File(s):** `backend/src/inkstave/compile/jobs.py`
- **Problem:** Spec 34 §5.2 states: "The compile-trigger endpoint **and** the
  compile ARQ job entry both verify COMPILE + membership for the requesting user."
  `_run_compile_body` (jobs.py:103-128) only calls `CompileRepository.get_by_id`
  and checks cancel/terminal status; it performs no membership/capability check.
  Defense-in-depth gap (the REST endpoint already authorizes before enqueue).
- **Fix to apply:** In `_run_compile_body`, before running the compile, load the
  requesting user/owner for the compile's project and re-verify the COMPILE
  capability / active membership against `project_memberships` (reuse the existing
  authorization helper/service the REST endpoint uses). If the check fails, fail the
  compile gracefully (mark it failed / record the reason) rather than running.
  Confine all changes to `jobs.py`. (If the in-scope constraint makes a full re-auth
  impossible without touching out-of-scope helpers, implement the minimal in-`jobs.py`
  membership re-check using existing imported repositories/services and document the
  decision in a code comment.)

### Issue 131 — sharing migration owner-backfill not verified
- **Source spec:** 33-collaborators-sharing
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_migrations.py`
- **Problem:** Spec 33 §8 requires a "Migration smoke: tables created; existing
  project owner backfilled to an owner membership." `test_migrations.py` only has
  round-trip and autogenerate-diff tests; nothing verifies the backfill INSERT
  populates `project_memberships` for pre-existing projects.
- **Fix to apply:** Add a test that downgrades to the revision **before** the
  sharing/memberships migration, inserts a project (and its owner user) at that
  revision, upgrades to head, and asserts an **owner** active membership row exists
  in `project_memberships` for that project's owner. Follow the existing
  Alembic-driver/test-DB pattern used in `test_migrations.py`.

### Issue 34 — file-tree migration root-backfill not verified
- **Source spec:** 12-file-tree-model
- **Severity:** minor
- **File(s):** `backend/tests/integration/test_migrations.py`
- **Problem:** Spec 12 §8 requires "Migration up/down smoke including backfill (one
  pre-existing project gets a root)." The tree migration (`8b301674ef53`) has a
  backfill `INSERT...SELECT` creating a root folder for projects lacking one, but
  `test_migration_round_trip` only runs `downgrade('base')` + `upgrade('head')`
  generically and never inserts a project to verify it receives a root.
- **Fix to apply:** Add a test that downgrades past the tree migration, inserts a
  project (+ owner user) lacking a root, upgrades to head, and asserts exactly one
  `is_root` folder now exists for that project. Reuse the same migration test
  harness as Issue 131.

### Issue 27 — register happy-path component test missing
- **Source spec:** 09-frontend-foundation
- **Severity:** minor
- **File(s):** `frontend/src/pages/register.test.tsx`
- **Problem:** Spec 09 §8 / AC2 require a component test for the register happy
  path: valid submission succeeds, redirects to `/login`, and shows a success
  message. `register.test.tsx` covers only mismatched passwords, duplicate 409, and
  422 field errors — the success-path redirect is untested (only the e2e covers it
  end-to-end).
- **Fix to apply:** Add a component test that fills valid, matching passwords,
  mocks a successful `201` register response, submits, and asserts navigation to
  `/login` with the `justRegistered`/success state and the success message. Reuse
  the existing route stub and the mocking style already in the file.

### Issue 102 — logparse truncation direction contradicts spec wording
- **Source spec:** 27-compile-error-annotations
- **Severity:** nit
- **File(s):** `backend/src/inkstave/logparse/service.py`
- **Problem:** Spec §5.5 says logs are "truncated from the end" (keep the
  beginning), but `service.py:57` does `data = data[-limit:]` (keeps the **tail**),
  with comment "final errors live at the end." ADR 0027 documents this intentional
  reversal, so impl + ADR agree, but the spec wording is formally contradicted. The
  implemented tail-keeping is correct for LaTeX.
- **Fix to apply:** Keep the tail-keeping behaviour (it is correct). Since the spec
  file is out of scope, strengthen the existing in-code comment at `service.py:57`
  to explicitly state that this **intentionally supersedes** the spec §5.5 wording
  ("truncated from the end" was imprecise) per ADR 0027 — final LaTeX errors live at
  the end, so the tail is kept. Do not change the slice direction.

### Issue 212 — route-template extraction unit test missing
- **Source spec:** 51-observability
- **Severity:** minor (adjusted from major)
- **File(s):** `backend/tests/unit/test_observability.py`
- **Problem:** Spec 51 §8 explicitly requires a unit test: "Route-template
  extraction returns the template, and `<unmatched>` for 404s." No such test exists;
  `_route_template` in `middleware.py` is only exercised indirectly via the
  `openapi.json` integration test (a matched route; no parameterized/404 case).
- **Fix to apply:** Add unit tests in `test_observability.py` that call
  `_route_template` (import it from the observability middleware module) against:
  (a) a matched **parameterized** route — e.g. `/api/v1/projects/{project_id}` — and
  assert the returned template equals the route template (not the concrete path);
  and (b) an **unmatched** path and assert it returns `<unmatched>`. Build the
  routes via a minimal FastAPI/Starlette app or the existing app fixture as needed
  for the helper's signature.

### Issue 166 — dead `monkeypatch` fixture parameter
- **Source spec:** 41-agent-foundation
- **Severity:** nit
- **File(s):** `backend/tests/unit/test_agent_llm.py`
- **Problem:** `test_fake_stream_is_deterministic` (test_agent_llm.py:27) declares
  `monkeypatch: pytest.MonkeyPatch` but never references it in the body — a dead
  fixture injection.
- **Fix to apply:** Remove the unused `monkeypatch: pytest.MonkeyPatch` parameter
  from `test_fake_stream_is_deterministic`. Do not change the test body's behaviour.

## 4. Acceptance criteria

1. **(Issue 77)** `jobs.py` stores `log_excerpt` as the **tail** of `log_text`
   (`[-2000:]`); a test with a long log proves the trailing error text is retained.
2. **(Issue 78)** `_cancel_watcher`'s flag-polling mechanism is documented in code
   as the intentional choice (or a pub/sub subscription is added entirely within
   `jobs.py`); cancellation still works and existing compile-cancel tests pass.
3. **(Issue 137)** `_run_compile_body` re-verifies COMPILE membership before running
   and fails gracefully on an unauthorized requester; existing compile tests pass.
4. **(Issue 131)** A migration test inserts a pre-membership project and asserts an
   owner active membership is backfilled after upgrade; it passes.
5. **(Issue 34)** A migration test inserts a pre-tree project and asserts exactly one
   `is_root` folder is backfilled after upgrade; it passes.
6. **(Issue 27)** A `register.test.tsx` test asserts a valid submission mocks a 201,
   navigates to `/login` with the success state, and shows the success message.
7. **(Issue 102)** `logparse/service.py` keeps the tail and its comment explicitly
   notes it supersedes the imprecise spec §5.5 wording per ADR 0027.
8. **(Issue 212)** Unit tests assert `_route_template` returns the parameterized
   template for a matched route and `<unmatched>` for an unmatched path.
9. **(Issue 166)** The unused `monkeypatch` parameter is removed; the test still
   passes.

## 5. Test plan

> All project tests combined must keep the suite under 2 minutes. No real LaTeX
> compile, LLM, or network in these tests — use existing fakes/test DB/fake Redis.

- **Existing green:** Run the backend pytest suites (compile, migrations,
  observability, agent unit) and the frontend register test before/after; all
  previously-passing tests must stay green.
- **New/updated backend tests (pytest):**
  - Long-log tail excerpt assertion for Issue 77 (in the nearest existing in-scope
    test; otherwise code-only with documented manual verification).
  - Owner-backfill (Issue 131) and root-backfill (Issue 34) migration tests in
    `test_migrations.py`.
  - `_route_template` matched-template and `<unmatched>` tests in
    `test_observability.py` (Issue 212).
  - Removal of the dead `monkeypatch` param in `test_agent_llm.py` (Issue 166).
- **New/updated frontend tests (Vitest + RTL):** register happy-path redirect test
  in `register.test.tsx` (Issue 27).
- **Performance/budget note:** Migration tests reuse the existing Alembic test-DB
  harness; route-template tests use a lightweight app; no real external calls.

## 6. Definition of Done

- [ ] All 9 issues in §3 fixed exactly as described.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; previously-green tests stay
      green.
- [ ] Only files listed in §2 were modified.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff + pyright/mypy backend; ESLint + Prettier
      + tsc frontend).
- [ ] No unrelated refactors; no Overleaf code copied.
