# Spec 76 — Fix-pack: backend test completeness & tool-output contracts (requirements)

## 1. Summary

This fix-pack applies **9 confirmed issues** drawn from specs
`06-user-model-registration`, `12-file-tree-model`, `29-collab-websocket`,
`37-history-api`, `42-agent-tools`, `48-agent-context-section-parsing`, and
`53-performance-test-speed`. Each was verified by two independent reviewers.

**Severity breakdown (adjusted):**

- **Major:** 1 — #222 N+1 bounded-query tests missing for history-list and
  collaborators-list endpoints (AC6).
- **Minor:** 4 — #146 HTTP 413 not exercised at the route; #167 `locate_section`
  method-label spec-42/48 note; #204 `locate_section` omits `start_char`/
  `end_char`/`char_range`; #111 cross-instance test asserts bytes, not CRDT
  convergence.
- **Nit:** 4 — #149 diff 404 for non-captured version; #148 cross-project label
  404 tested with random UUID only; #35 `safe_path` DEL (0x7F) case missing;
  #16 `password.py` named-function shims.

The work is mostly **integration/unit test completeness**, plus one real
tool-output fix (#204) and small contract/documentation alignments.

## 2. Files in scope

Edit **only** these files (exact payload set):

- `backend/src/inkstave/agent/tools/locate_section.py`
- `backend/src/inkstave/auth/password.py`
- `backend/tests/integration/test_history_api.py`
- `backend/tests/integration/test_performance_api.py`
- `backend/tests/unit/test_collab_ws_redis.py`
- `backend/tests/unit/test_safe_path.py`

> **Restrict-edits note:** Only `locate_section.py` and `password.py` are
> production sources; the rest are tests. Do not modify any route/service/model
> outside this list. If a new test needs a fixture that only exists in an
> out-of-scope conftest, reuse the existing fixtures (do not add new ones in
> out-of-scope files). Do not create new test files unless unavoidable; prefer
> adding cases to the listed test files.

## 3. Issues to fix

### Issue #222 — Bounded-query tests for history-list & collaborators-list (MAJOR)

- **Source spec:** 53-performance-test-speed (AC6 / §5.5).
- **File:** `backend/tests/integration/test_performance_api.py`.
- **Problem:** AC6 requires that the **project list, file tree, history list, and
  collaborators** list endpoints each issue a **bounded** number of queries.
  Project list and file tree are covered (the latter here as
  `test_file_tree_query_count_is_bounded`), but **history list** and
  **collaborators list** have **no** `query_counter` test.
- **Fix to apply:** Add two `query_counter`-based integration tests in this file
  (reuse the existing `query_counter` helper/fixture and the same pattern as
  `test_file_tree_query_count_is_bounded`):
  1. **History list:** seed a project with **N** history entries, GET the history
     list endpoint, and assert the query count is **bounded** (a small constant,
     independent of N — i.e. verify it does not grow with row count, ideally by
     running with two different N values or asserting `count <= K`).
  2. **Collaborators / members list:** seed a project with **N** collaborators,
     GET the collaborators list endpoint, and assert a **bounded** query count
     the same way.
  Use the eager-loading expectation from the existing covered endpoints as the
  template; assert no per-row lazy load.

### Issue #146 — HTTP 413 not exercised at the diff route (minor)

- **Source spec:** 37-history-api (AC11).
- **File:** `backend/tests/integration/test_history_api.py`.
- **Problem:** `test_diff_size_guard_413` (verified, ~lines 282–292) calls the
  service-layer `get_diff(...)` directly and only asserts `result.too_large is
  True`. The route's mapping
  `code = HTTP_413_REQUEST_ENTITY_TOO_LARGE if result.too_large` is never hit by
  an HTTP request, so AC11 ("the API responds 413") is unverified.
- **Fix to apply:** Add an integration test that **configures a tiny**
  `HISTORY_DIFF_MAX_BYTES` (via the existing settings-override mechanism used in
  the suite — monkeypatch/dependency override, not editing config files) and
  issues an `async_client.get(...)` to the **diff endpoint** for a diff large
  enough to exceed the limit, asserting **HTTP 413**. Keep the existing
  service-level assertion test too.

### Issue #149 — Diff 404 for non-captured version not tested (nit)

- **Source spec:** 37-history-api (§5.2.3).
- **File:** `backend/tests/integration/test_history_api.py`.
- **Problem:** §5.2.3 says "404 if either version is not captured". No test GETs
  the diff endpoint with a non-existent version and asserts 404.
- **Fix to apply:** Add a test that GETs
  `.../history/diff?from=999&to=current` (or `to=999`) for a version that does
  not exist and asserts **HTTP 404**. Use the existing project/auth fixtures.

### Issue #148 — Cross-project label 404 tested with random UUID only (nit)

- **Source spec:** 37-history-api (§8; criterion 10).
- **File:** `backend/tests/integration/test_history_api.py`.
- **Problem:** `test_delete_missing_label_404` (verified, ~lines 271–279) uses a
  **random** `uuid4()`, which only exercises the "not found" branch. A real
  cross-project access (a valid label belonging to **project B** accessed via
  **project A**'s URL with a token authorized on A) is not tested, so the
  wrong-project branch is unverified.
- **Fix to apply:** Add a test that:
  1. creates a label in **project B**;
  2. DELETEs it via **project A**'s URL using a token authorized on project A;
  3. asserts **HTTP 404**.
  Reuse existing multi-project/auth fixtures. Keep or fold the existing
  random-UUID not-found test (do not regress the not-found branch).

### Issue #167 — `locate_section` method-label spec-42/48 note (minor)

- **Source spec:** 42-agent-tools (§5.2.6) / 48 (ADR-0048).
- **File:** `backend/src/inkstave/agent/tools/locate_section.py`.
- **Problem:** `locate_section` returns `method="structure-v1"` (verified, line
  77) while spec 42 §5.2.6 specifies `method="heuristic-v1"`. The change is a
  deliberate spec-48 upgrade documented in ADR-0048, but the spec-42 literal
  contract is unmet and confusing.
- **Fix to apply:** This is documentation/clarity, **not** a behaviour change —
  **keep** the returned label `"structure-v1"` (it is the spec-48 upgrade; do not
  break tests asserting it). Add a brief **code comment** at the
  `ToolResult.success(..., method="structure-v1")` site noting that the method
  label was upgraded from spec-42's `"heuristic-v1"` to `"structure-v1"` in spec
  48 (cross-reference ADR-0048). Do not edit spec files or ADRs (out of scope);
  the comment lives in `locate_section.py`.

### Issue #204 — `locate_section` omits char offsets (minor)

- **Source spec:** 48-agent-context-section-parsing (§5.2).
- **File:** `backend/src/inkstave/agent/tools/locate_section.py`.
- **Problem:** §5.2 states `locate_section` should return `file_path, start_line,
  end_line, char_range, and a confidence/score`. The serialized result (verified,
  lines ~63–76) includes `start_line`/`end_line`/`score` but **omits**
  `start_char`/`end_char`/`char_range`, even though `SectionMatch.node` carries
  those fields. Callers cannot use the character offsets.
- **Fix to apply:** Add the character offsets to each result dict in
  `locate_section.py`, sourced from `m.node.start_char` / `m.node.end_char`
  (matching the existing serialization style). Expose them as `start_char` and
  `end_char` (and/or a `char_range` tuple/object) consistently. Ensure the values
  are JSON-serializable. If a test asserts the result shape, **extend** that
  assertion to include the new fields (only if the test is within this fix-pack's
  scope — `test_agent_tools.py` is **not** in scope, so do **not** edit it; the
  added fields are additive and must not break existing assertions, which check
  for presence of specific keys/equality on existing keys only).

### Issue #111 — Cross-instance test asserts bytes, not CRDT convergence (minor)

- **Source spec:** 29-collab-websocket (criterion 5).
- **File:** `backend/tests/unit/test_collab_ws_redis.py`.
- **Problem:** `test_cross_instance_room_delivery` (verified, ~lines 54–102)
  asserts only that the **raw payload bytes** reach the receiver's queue
  (`receiver.send_queue.get_nowait() == b'\x00update'`) and the sender queue is
  empty. Criterion 5 requires "the receiver applies it and converges" — i.e.
  document equality, not just byte delivery.
- **Fix to apply:** Extend the test so the receiver **applies** the relayed
  update to a `YDocument` (the project's pycrdt-backed doc type used elsewhere)
  and asserts **text equality** with the sender's doc after applying. Keep the
  existing byte-delivery and no-echo assertions. (The payload `b'\x00update'`
  used in the current test is a placeholder; use a **real** Yjs update produced
  from the sender doc so applying it yields convergence — generate the update
  from the sender's `YDocument` rather than a hand-rolled byte string.) The test
  may stay in the unit tier; converging two in-process docs is sufficient and
  fast.

### Issue #35 — `safe_path` DEL (0x7F) case missing (nit)

- **Source spec:** 12-file-tree-model.
- **File:** `backend/tests/unit/test_safe_path.py`.
- **Problem:** The spec says reject "no NUL or other ASCII control chars
  (\x00–\x1f, \x7f)". The implementation correctly rejects `0x7F`, and tests
  cover `\x00` and `\x1f`, but **not** `\x7f` (DEL).
- **Fix to apply:** Add a `del\x7fchar` case to the `invalid_names` parametrize
  list, asserting it is rejected. Match the existing case style.

### Issue #16 — `password.py` named-function shims (nit)

- **Source spec:** 06-user-model-registration (§5.2.1).
- **File:** `backend/src/inkstave/auth/password.py`.
- **Problem:** §5.2.1 prescribes module-level `hash_password(plain: str) -> str`
  and `verify_password(plain: str, hashed: str) -> bool`. The implementation
  (verified) exposes a `PasswordHasher` class with `.hash()` / `.verify()`
  (documented in ADR-0005). The class is the chosen, superior design, but the
  exact named module functions are absent.
- **Fix to apply:** Add thin **module-level** `hash_password(plain) -> str` and
  `verify_password(plain, hashed) -> bool` functions in `password.py` that
  delegate to a **default `PasswordHasher` instance**. Do not remove or change
  the class (ADR-0005 stands); the functions satisfy the §5.2.1 named contract.
  Keep types precise and behaviour identical to the class methods.

## 4. Acceptance criteria

1. **Bounded list queries (#222):** New `query_counter` tests prove the
   **history-list** and **collaborators-list** endpoints issue a bounded
   (row-count-independent) number of queries.
2. **HTTP 413 (#146):** A test GETs the diff endpoint with a tiny configured
   `HISTORY_DIFF_MAX_BYTES` and asserts **413**.
3. **Diff 404 (#149):** A test GETs the diff endpoint with a non-captured version
   and asserts **404**.
4. **Cross-project label 404 (#148):** A label created in project B, deleted via
   project A's URL (token authorized on A), returns **404**.
5. **Method-label note (#167):** `locate_section.py` carries a comment explaining
   the `"structure-v1"` upgrade vs spec-42 `"heuristic-v1"` (ADR-0048); behaviour
   unchanged.
6. **Char offsets (#204):** `locate_section` results include `start_char` /
   `end_char` (and/or `char_range`) sourced from `m.node`; existing assertions
   unbroken.
7. **CRDT convergence (#111):** The cross-instance test applies the relayed
   update to a `YDocument` and asserts text equality with the sender's doc.
8. **DEL char (#35):** `test_safe_path` rejects a `\x7f`-containing name.
9. **Named password functions (#16):** `hash_password` / `verify_password`
   module-level functions exist and delegate to a default `PasswordHasher`;
   class unchanged.

## 5. Test plan

> The whole suite must stay under 2 minutes; all slow work stays stubbed.

- **Existing green:** Run pytest before/after; keep green.
- **Integration (pytest + httpx / test DB):**
  - `test_performance_api.py`: history-list and collaborators-list bounded-query
    tests (#222/AC1).
  - `test_history_api.py`: HTTP-413 via tiny `HISTORY_DIFF_MAX_BYTES` (#146/AC2),
    diff-404 for non-captured version (#149/AC3), cross-project label 404
    (#148/AC4).
- **Unit (pytest):**
  - `test_collab_ws_redis.py`: apply a real Yjs update to a receiver `YDocument`
    and assert convergence (#111/AC7).
  - `test_safe_path.py`: add the `\x7f` rejection case (#35/AC8).
  - A small unit test (in an in-scope file, or covered implicitly) that
    `hash_password`/`verify_password` round-trip and reject wrong passwords
    (#16/AC9). If no in-scope test file fits without an out-of-scope edit, the
    existing password tests must still pass and the new functions must be
    type-checked; do not edit out-of-scope test files.
- **Production-source changes:** `locate_section.py` (#167 comment, #204 char
  offsets) and `password.py` (#16 shims) are additive; ensure existing tests
  (even if out of scope) still pass with the additive output keys/functions.
- **Performance/budget note:** All new tests are fast DB-integration or
  in-process unit tests; no LaTeX/LLM/real network; no real timers.

## 6. Definition of Done

- [ ] All 9 issues in §3 applied; no files outside §2 touched.
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; full suite < 2 minutes.
- [ ] `locate_section` char-offset fields are additive and break no existing
      assertion; method-label behaviour unchanged.
- [ ] `password.py` named functions delegate to `PasswordHasher`; class intact.
- [ ] Lint/format/type-check clean (ruff + mypy/pyright).
- [ ] No unrelated refactors; no Overleaf code copied; no out-of-scope edits.
