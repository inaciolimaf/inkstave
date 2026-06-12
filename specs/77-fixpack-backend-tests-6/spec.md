# Spec 77 — Fix-pack: backend & frontend test-coverage gaps (batch 6) (requirements)

## 1. Summary

This fix-pack remediates **9 confirmed issues** — all from validation review of
already-implemented specs — whose files are disjoint from every other fix-pack.
Every issue is a **test-coverage / spec-deviation gap**: the acceptance criteria
or test plan of the source spec demanded an assertion or test that was never
written, even though the production code is correct. Applying these fixes makes
the originally required coverage real.

**Fixes:** 9 issues across 5 files.

**Severity breakdown:** 0 major · 5 minor · 4 nit.

| ID  | Source spec | Severity | Area |
|-----|-------------|----------|------|
| 200 | 48-agent-context-section-parsing | minor | parser: all sectioning levels |
| 201 | 48-agent-context-section-parsing | minor | parser: `\subfile` detection |
| 202 | 48-agent-context-section-parsing | minor | parser: `char_range` (AC1) |
| 203 | 48-agent-context-section-parsing | minor | select_context: priority ordering |
| 205 | 48-agent-context-section-parsing | nit | select_context: surrounding-lines config |
| 21  | 07-jwt-authentication | minor | logout revokes whole token family (AC7) |
| 66  | 18-editor-ui-codemirror | nit | editor-pane mock strategy vs spec (MSW) |
| 171 | 42-agent-tools | minor | viewer read-tools coverage (AC6) |
| 145 | 37-history-api | minor | `text_from_state` unit contract (§5.4.2) |

## 2. Files in scope

Edit **only** these files (exact payload set):

- `backend/tests/integration/test_agent_tools.py`
- `backend/tests/integration/test_auth.py`
- `backend/tests/unit/test_agent_context.py`
- `backend/tests/unit/test_history_diff.py`
- `frontend/src/features/editor/editor-pane.test.tsx`

**Restrict edits to the files above.** Do not modify production source, other
tests, fixtures, or config. These are all test files; the code under test is
already correct. If a test needs an import (e.g. `text_from_state`,
`reconstruct_state`, a parser node kind, a tool class), import it from the
existing production module — do not add new production code.

## 3. Issues to fix

### Issue 200 — All sectioning levels + nesting must be tested
- **Source spec:** 48-agent-context-section-parsing · **Severity:** minor
- **File:** `backend/tests/unit/test_agent_context.py`
- **Problem:** Spec 48 §8 (lines 245–246) requires "table-driven fixtures
  covering all sectioning levels + nesting". `test_parse_nesting_levels_and_ranges`
  (around line 43) only asserts `section` (level 1), `subsection` (level 2), and
  `section*`. The levels `part` (-1), `chapter` (0), `subsubsection` (3),
  `paragraph` (4), and `subparagraph` (5) are never tested. The parser supports
  them but nothing asserts their level/ranges.
- **Fix to apply:** Extend the table-driven fixture in
  `test_parse_nesting_levels_and_ranges` (or add a sibling test) so the input
  LaTeX includes `\part`, `\chapter`, `\subsubsection`, `\paragraph`, and
  `\subparagraph` headings in addition to the existing ones. Assert each node's
  command, title, and **level** (`part`→-1, `chapter`→0, `section`→1,
  `subsection`→2, `subsubsection`→3, `paragraph`→4, `subparagraph`→5) and
  `start_line`/`end_line` ranges, demonstrating correct nesting.

### Issue 201 — `\subfile{}` detection must be tested
- **Source spec:** 48-agent-context-section-parsing · **Severity:** minor
- **File:** `backend/tests/unit/test_agent_context.py`
- **Problem:** Spec 48 §8 (line 247) lists "`\input`/`\include`/`\subfile`
  detection". `test_parse_captures_label_and_inputs` (around line 64) only covers
  `\input` and `\include`. The parser regex (`(input|include|subfile)`) supports
  `\subfile`, but no test asserts it.
- **Fix to apply:** Extend the input-detection test so the fixture LaTeX contains a
  `\subfile{path/to/part}` reference, and assert it is captured as an INPUT node
  (same node kind/representation the test already asserts for `\input`/`\include`,
  e.g. an input node whose target path is `path/to/part`).

### Issue 202 — AC1 `char_range` must be validated
- **Source spec:** 48-agent-context-section-parsing · **Severity:** minor
- **File:** `backend/tests/unit/test_agent_context.py`
- **Problem:** AC1 (spec.md lines 206–207) requires "accurate 1-based
  start_line/end_line **and char_range** for each node"; §5.1 (lines 101–102)
  defines `start_char`/`end_char`. The existing tests assert only
  `(command, title, level, start_line, end_line)` tuples. A grep for
  `start_char`/`end_char`/`char_range` returns nothing — the char offsets are
  populated but never checked.
- **Fix to apply:** In `test_agent_context.py`, add assertions on concrete
  `start_char`/`end_char` values for at least one section node. Assert that a
  section's `start_char` equals the byte/character offset of its heading in the
  source and that its `end_char` extends to just before the next sibling's heading
  (consistent with how the parser computes ranges). Use a fixture whose offsets
  are deterministic so the asserted numbers are stable.

### Issue 203 — `select_context` priority ordering must be tested
- **Source spec:** 48-agent-context-section-parsing · **Severity:** minor
- **File:** `backend/tests/unit/test_agent_context.py`
- **Problem:** Spec 48 §8 (line 252) requires "priority ordering" to be tested for
  `select_context`. `test_select_respects_budget_and_truncates` and
  `test_select_includes_outline_summary` each use `any(c.kind == 'section')` /
  `any(c.kind == 'outline')` independently; neither asserts that section chunks
  (priority 0) precede the outline chunk (priority 1) in `bundle.chunks`.
- **Fix to apply:** Add an assertion (extend an existing test or add a new one)
  that in the returned `bundle.chunks`, the index of every `section` chunk is less
  than the index of the `outline` chunk — i.e. all priority-0 chunks appear before
  the priority-1 outline chunk.

### Issue 205 — `surrounding_lines` config must be shown to widen the window
- **Source spec:** 48-agent-context-section-parsing · **Severity:** nit
- **File:** `backend/tests/unit/test_agent_context.py`
- **Problem:** Spec 48 §8 (line 253) requires "surrounding-lines config respected".
  `test_select_respects_budget_and_truncates` passes `surrounding_lines=5` but
  only asserts budget+truncation; it never verifies the config actually changes
  the content window (no comparison against `surrounding_lines=0`).
- **Fix to apply:** Add a test that calls `select_context` twice over the same
  section/document — once with `surrounding_lines=0` and once with a larger value
  (e.g. `surrounding_lines=3`) — and asserts the returned section chunk's text is
  **strictly longer / contains more boundary lines** with the larger value. Assert
  the specific extra lines before/after the section boundary appear only in the
  wider result.

### Issue 21 — Logout revokes the whole token family (AC7)
- **Source spec:** 07-jwt-authentication · **Severity:** minor
- **File:** `backend/tests/integration/test_auth.py`
- **Problem:** AC7 requires that after logout, "a subsequent POST /auth/refresh
  with that token (**or any token in its family**) returns 401".
  `test_logout_is_idempotent_and_revokes` (around lines 167–181) re-attempts only
  the original `pair["refresh_token"]` after logout; it never rotates first to
  obtain a second family member and confirm that member is also rejected.
- **Fix to apply:** In `test_logout_is_idempotent_and_revokes` (or a new test in
  the same file), first call `POST /auth/refresh` once to rotate the refresh token
  (obtaining a new token in the same family). Then logout. Then assert that
  **both** the rotated (current) refresh token **and** a prior family member token
  are rejected with **401** on `POST /auth/refresh`.

### Issue 66 — editor-pane mock strategy vs spec §8 (MSW)
- **Source spec:** 18-editor-ui-codemirror · **Severity:** nit
- **File:** `frontend/src/features/editor/editor-pane.test.tsx`
- **Problem:** Spec 18 §8 prescribes "Spec 13 API is mocked (MSW)". The tests use
  `vi.stubGlobal('fetch', vi.fn(...))` (lines ~86, 101, 109). MSW is not a project
  dependency. Both strategies mock the API, but the prescribed tooling is not used,
  leaving an undocumented deviation.
- **Fix to apply:** **Record the chosen mocking strategy in the test file**, since
  MSW is intentionally not a dependency in this project. Add a top-of-file comment
  in `editor-pane.test.tsx` explaining that the project mocks the Spec-13 document
  API by stubbing `fetch` via `vi.stubGlobal` rather than MSW (the lightweight,
  dependency-free strategy adopted project-wide), satisfying spec §8's intent
  ("the Spec-13 API is mocked"). Do **not** add MSW as a dependency. This converts
  an undocumented deviation into a recorded, intentional decision. (Optionally
  also confirm the existing fetch stubs already cover GET + PUT content paths; no
  behavioural change required.)

### Issue 171 — Viewer read-tools coverage (AC6)
- **Source spec:** 42-agent-tools · **Severity:** minor
- **File:** `backend/tests/integration/test_agent_tools.py`
- **Problem:** AC6 states "read tools still succeed for the viewer".
  `test_viewer_cannot_propose_but_can_read` (around lines 160–169) exercises only
  `ReadFileTool` with the viewer ctx. `SearchProjectTool`, `ListTreeTool`, and
  `LocateSectionTool` are never run as a viewer.
- **Fix to apply:** Extend `test_viewer_cannot_propose_but_can_read` (or add a
  sibling test using the same viewer ctx) to also run `SearchProjectTool`,
  `ListTreeTool`, and `LocateSectionTool` with the viewer ctx and assert each call
  **succeeds** (returns a normal result, not an authorization error). The existing
  `ProposeEditTool`-is-forbidden-for-viewer assertion stays.

### Issue 145 — `text_from_state` unit contract (§5.4.2)
- **Source spec:** 37-history-api · **Severity:** minor
- **File:** `backend/tests/unit/test_history_diff.py`
- **Problem:** Spec 37 §8 (line 328, under **Unit (pytest)**) lists "Text-extraction
  helper agrees with spec-36 `reconstruct_state` output (criterion contract
  §5.4.2)". `test_history_diff.py` only has diff tests + `is_binary`; it never
  imports `text_from_state` or `reconstruct_state`. The contract is only exercised
  implicitly in integration tests.
- **Fix to apply:** Add a **no-DB unit test** in `test_history_diff.py` that builds
  an in-process `pycrdt` document, populates a known text value, serialises its
  state to bytes (the same encoding `reconstruct_state` produces), calls
  `text_from_state(state)` (imported from the production `reconstruct` module), and
  asserts the extracted text equals the expected string. Cover at least a simple
  ASCII case and (if practical) a multibyte/unicode case so the contract is pinned.

## 4. Acceptance criteria

1. `test_agent_context.py` asserts parser node **levels and ranges** for `part`
   (-1), `chapter` (0), `section` (1), `subsection` (2), `subsubsection` (3),
   `paragraph` (4), and `subparagraph` (5) (issue 200).
2. `test_agent_context.py` asserts a `\subfile{...}` reference is captured as an
   INPUT node (issue 201).
3. `test_agent_context.py` asserts concrete `start_char`/`end_char` values for at
   least one section node, matching the parser's computed offsets (issue 202).
4. `test_agent_context.py` asserts every `section` chunk precedes the `outline`
   chunk by index in `bundle.chunks` (issue 203).
5. `test_agent_context.py` demonstrates `surrounding_lines` changes the window:
   the section chunk text is longer with a larger `surrounding_lines` than with
   `surrounding_lines=0` over the same input (issue 205).
6. `test_auth.py` rotates the refresh token, logs out, and asserts **both** the
   rotated token and a prior family member are rejected with 401 (issue 21).
7. `editor-pane.test.tsx` carries a top-of-file comment recording the
   `vi.stubGlobal`/fetch-stub mocking strategy as the project's intentional
   substitute for MSW per spec §8 (issue 66).
8. `test_agent_tools.py` runs `SearchProjectTool`, `ListTreeTool`, and
   `LocateSectionTool` as a viewer and asserts each succeeds (issue 171).
9. `test_history_diff.py` contains a no-DB unit test that calls `text_from_state`
   on an in-process pycrdt state and asserts the extracted text (issue 145).
10. The full test suite stays green and under 2 minutes; no production source files
    are modified.

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Existing green:** Run `backend/tests/unit/test_agent_context.py`,
  `test_history_diff.py`, `test_auth.py`, `test_agent_tools.py`, and
  `frontend/src/features/editor/editor-pane.test.tsx` before changes to confirm
  baseline green.
- **New/updated tests:** All additions are assertions/tests in the five in-scope
  test files (no DB needed for the unit additions; the auth and agent-tools
  additions reuse the existing integration fixtures). Reuse existing fixtures,
  clients, and helpers; do not add new dependencies (notably no MSW).
- **Run:**
  - `pytest backend/tests/unit/test_agent_context.py backend/tests/unit/test_history_diff.py backend/tests/integration/test_auth.py backend/tests/integration/test_agent_tools.py`
  - `npm --prefix frontend run test -- editor-pane`
- **Performance/budget note:** These are assertion-level additions on existing
  fast tests plus one pure in-process pycrdt unit test; negligible runtime impact.

## 6. Definition of Done

- [ ] All 9 issues (200, 201, 202, 203, 205, 21, 66, 171, 145) fixed exactly as
      described in §3.
- [ ] All acceptance criteria in §4 pass.
- [ ] Only the five files in §2 are modified.
- [ ] No production/source code changed; no new dependencies added.
- [ ] Affected backend (pytest) and frontend (Vitest) suites are green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] No Overleaf code copied.
