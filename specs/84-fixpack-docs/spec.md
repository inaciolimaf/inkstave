# Spec 84 — Fix-pack: docs, ADR alignment & test-coverage gaps (requirements)

## 1. Summary

This fix-pack remediates nine confirmed issues. It is **docs-focused**: most
issues are reconciliations between the implemented code and its documentation —
the ADR for agent streaming, the per-run cost formula, the S3 streaming contract,
the `OutputStore` constructor signature, and the spec-55 hardening changelog
runtime table. The remaining issues add missing component-level tests for the
diff-review dialog (accept-all/reject-all, accessibility, base-changed banner) and
the share dialog (transfer-ownership confirm). Each is a localised doc edit or a
focused added test. The files in scope are disjoint from all other fix-packs, so
this work is parallel-safe.

## 2. Files in scope

Edit **only** these files (exact set from the validation payload):

- `backend/docs/adr/0044-agent-api-streaming.md`
- `backend/src/inkstave/agent/nodes.py`
- `backend/src/inkstave/compile/outputs.py`
- `backend/src/inkstave/storage/s3.py`
- `docs/refactors/55-hardening.md`
- `frontend/src/features/diff-review/DiffReviewDialog.test.tsx`
- `frontend/src/features/sharing/ShareDialog.test.tsx`

Do not modify any file outside this list. Other fix-packs may be editing other
files at the same time. If a fix appears to require touching an out-of-scope
file, stop and flag it rather than expanding scope.

## 3. Issues to fix

### Issue 195 — AC3 accept-all/reject-all not tested at component level (major)

- **Source spec:** 47-diff-review-ui
- **File(s):** `frontend/src/features/diff-review/DiffReviewDialog.test.tsx`
- **Problem:** AC3 requires: "when the user clicks reject-all then accept-all for
  that file, then all hunks flip and the counter and preview reflect it." There is
  no test for accept-all/reject-all in `DiffReviewDialog.test.tsx`. The `setAll`
  function exists and is wired in the component, but the component-level behaviour
  (counter change, all switches flipping) is untested.
- **Fix to apply:** Add a Vitest test that renders `DiffReviewDialog` with a
  multi-hunk file, clicks **reject-all** then **accept-all** for that file, and
  asserts: (a) all hunk switches flip to the expected state in each step, and
  (b) the accepted-hunk counter and the preview reflect the change. Use the same
  rendering harness/fixtures and the same accessible names (button labels) the
  component already exposes for the accept-all/reject-all controls.

### Issue 197 — AC11 accessibility not tested (minor)

- **Source spec:** 47-diff-review-ui
- **File(s):** `frontend/src/features/diff-review/DiffReviewDialog.test.tsx`
- **Problem:** AC11 requires verification that add/remove lines are conveyed
  non-visually (sr-only labels), hunk toggles are keyboard-operable, and the apply
  dialog traps focus. No test exercises keyboard navigation or checks sr-only text.
- **Fix to apply:** Add Vitest test(s) asserting:
  1. sr-only "added"/"removed" labels exist for added/removed lines (query by the
     sr-only text the component renders);
  2. a hunk toggle is operable via keyboard (focus + Enter/Space toggles it); and
  3. the apply confirmation dialog traps focus (focus stays within the dialog when
     tabbing). Use Testing Library + `userEvent` keyboard APIs; assert against the
     affordances the component actually renders (do not change component markup).

### Issue 196 — AC7 base-changed banner / blocked hunk not tested in component (major)

- **Source spec:** 47-diff-review-ui
- **File(s):** `frontend/src/features/diff-review/DiffReviewDialog.test.tsx`
- **Problem:** AC7 requires testing that when the live doc diverged, the
  base-changed warning banner is shown and blocked hunks are flagged disabled.
  This is tested only at the pure-function level (`hunks.test.ts` `blockedAgainst`).
  The dialog component has no test that seeds a diverged bridge/document, opens the
  dialog, and asserts the "This file changed since the proposal" banner appears and
  the affected switch is disabled.
- **Fix to apply:** Add a Vitest test that seeds a diverged document state (live
  doc differs from the proposal's `baseVersion`), opens `DiffReviewDialog`, and
  asserts: (a) the base-changed banner ("This file changed since the proposal" or
  the exact copy the component renders) is shown; (b) the blocked hunk's switch is
  disabled; and (c) the blocked hunk is excluded from apply. Use the same fixtures
  and bridge/document test double the component tests already use.

### Issue 180 — Token streaming uses complete() not stream() (nit, documented deviation)

- **Source spec:** 44-agent-api-streaming
- **File(s):** `backend/src/inkstave/agent/nodes.py`,
  `backend/docs/adr/0044-agent-api-streaming.md`
- **Problem:** Spec §5.4.1 states "use `LLMClient.stream` for the plan/respond LLM
  calls so tokens flow." The implementation uses `deps.llm.complete()` (nodes.py
  ~line 90) and re-chunks the full response into token events post-completion
  (`_chunk(response.content)`, ~lines 103–105). The departure is already documented
  in ADR 0044 §3, but clients do not receive truly incremental tokens.
- **Fix to apply:** This is an accepted, documented deviation. **Do not** rewrite
  the graph to use `stream()` (that risks the deterministic-tests / tool-call
  correctness the ADR protects). Instead:
  1. In `nodes.py`, add a short clarifying comment at the `complete()` call site
     pointing to ADR 0044 §3 as the rationale for re-chunking rather than true
     streaming (no behaviour change).
  2. In `backend/docs/adr/0044-agent-api-streaming.md`, ensure §3 explicitly and
     clearly records that this is a **deliberate deviation from spec 44 §5.4.1**
     (use `complete()` + post-completion `_chunk`, not `LLMClient.stream`), with
     the justification (full response needed for `tool_calls`/`usage`; tests
     deterministic) and a note that true incremental token streaming is a future
     refinement. Tighten the wording if §3 is vague.

### Issue 209 — Per-run cost check uses averaged rate (nit)

- **Source spec:** 49-agent-safety-evals
- **File(s):** `backend/src/inkstave/agent/nodes.py`
- **Problem:** The per-run mid-run budget checkpoint in `nodes.py` (~line 82)
  computes `cost = total / 1000 * deps.cost_per_1k` using the average of input and
  output rates, while spec §5.2 (`BudgetTracker`) says
  `cost = prompt*in_rate + completion*out_rate`. The helpers `cost_for()`,
  `run_cost_exceeded()`, and `run_tokens_exceeded()` exist in `budget.py` and are
  used correctly elsewhere (`jobs.py` rollup) but not in the live mid-run gate.
- **Fix to apply:** Change the mid-run budget checkpoint in `nodes.py` to use the
  prompt/completion split rather than the averaged single rate. Prefer reusing the
  existing `cost_for()` (and/or `run_cost_exceeded()` / `run_tokens_exceeded()`)
  helper from `budget.py` so the mid-run gate and the rollup use the same formula.
  Pass the prompt/completion token counts and their respective rates. Do not change
  `budget.py` (out of scope) — only call its existing exports from `nodes.py`. If
  the prompt/completion split is not available at the checkpoint, source it from
  the same usage object already tracked for the run.

### Issue 45 — S3ObjectStore does not stream GET (nit, documented trade-off)

- **Source spec:** 14-binary-file-storage
- **File(s):** `backend/src/inkstave/storage/s3.py`
- **Problem:** Spec §5.1 states "get/open must not load the whole object into
  memory." `S3ObjectStore.open()` buffers the full body before returning
  (`data = await resp['Body'].read()`, ~line 93), then re-chunks it. This violates
  the streaming contract for the S3 backend.
- **Fix to apply:** Prefer the real streaming fix: iterate over the aiobotocore
  `StreamingBody` (`resp['Body']`) in configurable-size chunks (default 64 KiB,
  matching the `LocalObjectStore` chunk size / settings) and yield each chunk,
  instead of `read()`-ing the whole body into memory. Preserve the existing
  `open()` async-generator contract and signature. If, after investigation,
  incremental streaming of the aiobotocore body cannot be done safely within this
  pack's scope, then **fall back to documenting the limitation explicitly**: add a
  clear code comment at the `read()` site stating the S3 backend buffers the whole
  object (accepted trade-off) and reference the ADR — but the streaming
  implementation is the preferred outcome.

### Issue 132 — Transfer-ownership confirm dialog not tested (minor)

- **Source spec:** 33-collaborators-sharing
- **File(s):** `frontend/src/features/sharing/ShareDialog.test.tsx`
- **Problem:** §8 requires Vitest tests for "confirm dialogs for destructive
  actions (remove/revoke/transfer) (AC 11)." Tests for remove and revoke confirm
  dialogs exist, but there is no test for the transfer-ownership confirm path.
  `api.transferOwnership` is mocked but never called in any test.
- **Fix to apply:** Add a Vitest test that clicks the **Transfer** button, confirms
  the `AlertDialog`, and asserts `api.transferOwnership` is called with the correct
  arguments (project id + target member/user id, matching the component's call).
  Mirror the existing remove/revoke confirm-dialog tests' structure.

### Issue 234 — Changelog omits single-threaded `just test` timing (nit)

- **Source spec:** 55-refactor-hardening
- **File(s):** `docs/refactors/55-hardening.md`
- **Problem:** The runtime table in the changelog records `pytest -n auto` timings
  (and `-n 4`) but not the single-threaded `just test` timing, which the baseline
  shows takes ~3m01s (above the 2-minute budget). AC6 requires before/after
  runtimes be recorded; the single-threaded default is unacknowledged.
- **Fix to apply:** Add a row to the runtime table for the single-threaded
  `just test` timing (~3m01s baseline) and add an explicit note that the
  single-threaded default run exceeds the 2-minute budget, and that the budget is
  measured under xdist (`-n auto`). Keep the existing rows intact; match the
  table's existing column layout and wording style.

### Issue 88 — OutputStore.__init__ missing logger parameter (nit)

- **Source spec:** 23-output-storage
- **File(s):** `backend/src/inkstave/compile/outputs.py`
- **Problem:** Spec §5.2.2 lists `logger` as a constructor parameter:
  `def __init__(self, *, storage, repo, settings, logger)`. The implementation
  (~line 95) omits it, using structlog's module-level binding instead:
  `def __init__(self, *, storage, repo, settings)`. Functionally fine, but the API
  deviates from the spec contract.
- **Fix to apply:** Add an optional, keyword-only `logger` parameter to
  `OutputStore.__init__`, defaulting to the existing module-level structlog logger
  (so existing call sites are unaffected). Use the injected logger inside the class
  where the module logger is currently used. Keep the keyword-only signature shape
  consistent with the rest of the constructor. Do not change any out-of-scope call
  sites; the default must keep them working unchanged.

## 4. Acceptance criteria

1. **(195)** A `DiffReviewDialog.test.tsx` test clicks reject-all then accept-all
   for a file and asserts all hunk switches flip and the counter/preview update.
2. **(197)** Tests assert sr-only "added"/"removed" labels exist, a hunk toggle is
   keyboard-operable, and the apply dialog traps focus.
3. **(196)** A `DiffReviewDialog.test.tsx` test seeds a diverged document, asserts
   the base-changed banner renders, the blocked hunk's switch is disabled, and the
   blocked hunk is excluded from apply.
4. **(180)** `nodes.py` has a comment at the `complete()` site referencing ADR
   0044 §3, and ADR 0044 §3 explicitly records the deliberate deviation from spec
   44 §5.4.1 with its justification.
5. **(209)** The mid-run budget checkpoint in `nodes.py` uses the prompt/completion
   split (via `cost_for()` / `run_cost_exceeded()` / `run_tokens_exceeded()`),
   not the averaged single rate.
6. **(45)** `S3ObjectStore.open()` streams the body in configurable chunks without
   buffering the whole object — or, if not feasible, the buffering limitation is
   explicitly documented in-code as an accepted trade-off.
7. **(132)** A `ShareDialog.test.tsx` test confirms the transfer-ownership
   AlertDialog and asserts `api.transferOwnership` is called with the right args.
8. **(234)** The spec-55 hardening changelog runtime table includes the
   single-threaded `just test` timing and notes it exceeds the budget (budget
   measured under xdist).
9. **(88)** `OutputStore.__init__` accepts an optional keyword-only `logger`
   defaulting to the module logger, and uses it internally; existing call sites
   remain valid.

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Existing tests stay green:** Run the affected backend pytest modules (agent,
  compile/outputs, storage) and the frontend Vitest suites for diff-review and
  sharing. All currently passing tests must remain green.
- **New/updated frontend tests (Vitest):** the three diff-review tests
  (accept-all/reject-all, accessibility, base-changed banner) and the
  transfer-ownership confirm test. All use mocked APIs and seeded fixtures — no
  real network.
- **New/updated backend tests (pytest):** if the `nodes.py` cost change or the
  `outputs.py` logger param needs a guard, add/extend a focused unit test with the
  existing in-memory doubles; otherwise rely on the existing budget/output tests
  staying green. The S3 streaming change must keep existing `s3.py` tests green
  (using the moto/aiobotocore stub the tests already use); add a chunking
  assertion only if it fits the existing harness cheaply.
- **Performance/budget note:** all additions are pure unit/component tests with
  mocked dependencies; the full suite stays under 2 minutes.

## 6. Definition of Done

- [ ] All nine issues in §3 fixed (195, 197, 196, 180, 209, 45, 132, 234, 88).
- [ ] All acceptance criteria in §4 pass.
- [ ] All new/updated tests in §5 written and green; pre-existing tests still
      green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff for Python; ESLint/Prettier + strict TS
      for frontend).
- [ ] Only files listed in §2 were modified.
- [ ] No Overleaf code copied.
