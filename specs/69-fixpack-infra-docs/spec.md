# Spec 69 — Fix-Pack: Infra & Docs (test-budget gate) (requirements)

## 1. Summary

This fix-pack resolves **13 confirmed issues** from specs 01–57 that all live in
the test-budget / CI / infra-docs layer. The dominant theme — flagged by **two
CRITICAL** issues (`#221`, `#239`) and several major/minor duplicates (`#8`,
`#11`, `#12`, `#92`, `#161`, `#10`, `#107`) — is that the **default `just test`
recipe and the CI pytest stages do not pass `-n auto`** (pytest-xdist). The
backend fast tier is ~3 m 01 s single-threaded but the project's hard budget is
**< 2 minutes**, which is only met under xdist (as `scripts/run_timed.sh`
already does). The remaining issues cover: a slow-test detector that is fed a
hardcoded empty `slowest: []` list (`#231`, `#223`), a CI job graph that is
sequential despite the ADR claiming parallel jobs (`#12`), a stale ADR baseline
(`#14`), and a trivial ruff `extend-exclude` wording note (`#2`).

**Severity breakdown (adjusted):**
- critical: 2 (`#221`, `#239`)
- major: 3 (`#12`, `#223`, and `#11` adjusted to major)
- minor: 4 (`#8`, `#92`, `#161`, and `#231`)
- nit: 4 (`#2`, `#14`, `#107`, `#10`)

> `#8`, `#11`, `#92`, `#161`, `#10`, `#107`, `#221`, `#239` are **the same root
> defect** (missing `-n auto`) seen from different specs. Fix it **once,
> thoroughly**, in the CI workflow, `pyproject.toml` addopts, and the `justfile`
> default recipe, matching the `run_timed.sh` path. Then each per-spec criterion
> is satisfied by that single change.

## 2. Files in scope

Edit **only** these files. They are disjoint from all other fix-packs.

```
backend/pyproject.toml
backend/scripts/check_test_budget.py
docs/adr/0004-testing-foundation.md
docs/refactors/25-compilation.md
.github/workflows/ci.yml
justfile
scripts/run_timed.sh
```

**NOTE:** The payload listed the CI file as `github/workflows/ci.yml`; the real
path is **`.github/workflows/ci.yml`** (with the leading dot) — that is the file
in scope. Restrict all edits to the paths above; if a fix appears to need another
file, stop and report.

## 3. Issues to fix

### 3.1 — `#221` + `#239` (CRITICAL) + `#11`/`#8`/`#92`/`#161`/`#10`/`#107`: CI/default pytest missing `-n auto`

- **Files:** `.github/workflows/ci.yml`, `backend/pyproject.toml`, `justfile`,
  `scripts/run_timed.sh` (reference — already uses `-n auto`)
- **Problem:** The 2-minute budget is only achievable with pytest-xdist (`-n
  auto`). Today:
  - `.github/workflows/ci.yml` runs the **unit** stage (~line 96) and the
    **integration** stage (~line 131) **without** `-n auto`.
  - `backend/pyproject.toml` `addopts` (~line 101) omits `-n auto`, and the comment
    at ~line 100 falsely claims "CI adds `-n auto` for parallel wall-clock".
  - `justfile` `test:` recipe (~lines 26–27) runs
    `uv run --project backend pytest backend/tests` with no `-n auto`; only
    `test-timed` → `scripts/run_timed.sh` parallelizes.
  The measured baseline is **~3 m 01 s single-threaded**, so the budget gate
  (`check_test_budget.py`, which sums per-stage wall-clock) would exceed 120 s and
  **fail the build**. `conftest` already provisions per-worker databases via
  `PYTEST_XDIST_WORKER`, so xdist is safe to enable.
- **Fix (apply all three, so the default, the CI gate, and the timed script agree):**
  1. **`.github/workflows/ci.yml`:** Add `-n auto` to **both** the unit pytest
     invocation (~line 96) and the integration pytest invocation (~line 131),
     matching the form used in `run_timed.sh`. Do not change the marker
     expressions or coverage flags — only add the xdist flag.
  2. **`backend/pyproject.toml`:** Add `-n auto` to `addopts` so the project's
     default pytest run (including `just test`) is parallel by default, **and**
     correct/remove the now-misleading comment at ~line 100. (If you prefer not to
     bake `-n auto` into `addopts` because some local debugging runs want
     single-threaded, then instead add `-n auto` directly to the `just test`
     recipe — but the CI stages in step 1 MUST get the flag regardless.)
  3. **`justfile`:** Ensure the default `test:` recipe runs with `-n auto` (either
     inherited from `addopts` per step 2, or added explicitly to the recipe). The
     day-to-day `just test` must measure under the 2-minute budget, matching
     `test-timed`/`run_timed.sh`.
  After this, the comment in `pyproject.toml` that "CI adds `-n auto`" must be
  **true** (or removed), and `run_timed.sh`, `just test`, and CI all use xdist.
- **Verification:** `just test-timed` runs green under 120 s; `grep -n 'n auto'`
  in `ci.yml` shows it on both the unit and integration steps.

### 3.2 — `#231` + `#223` Slow-test detector is fed a hardcoded empty `slowest: []`

- **Files:** `scripts/run_timed.sh`, `backend/scripts/check_test_budget.py`,
  `.github/workflows/ci.yml`
- **Problem:** `run_timed.sh` (~line 28) and the CI budget step in `ci.yml`
  (~line 200) both write `"slowest": []` into `test-timing.json`.
  `check_test_budget.py` (~lines 57–65) iterates `timing.get('slowest', [])`,
  which is therefore **always empty** at the live gate, so the per-test
  `SLOW_TEST_FAIL_S` / `SLOW_TEST_WARN_S` detector (spec 53 §5.1 / §5.2.4 / AC5)
  never fires on real data. No `--junitxml` flag is passed to pytest, and no
  durations parser exists. The gate's unit tests pass only because they inject mock
  `slowest` data.
- **Fix:** Capture **real** per-test durations and feed them into the `slowest`
  array:
  1. Pass `--durations=0 -v` is noisy; instead emit machine-readable timings. The
     cleanest path is to add `--junitxml=<path>` to the timed pytest invocation in
     `run_timed.sh` (and the corresponding CI budget step in `ci.yml`), then parse
     the JUnit XML (each `<testcase>` has a `time` attribute) into a list of
     `{"id": <classname::name>, "duration_s": <float>}` entries, take the slowest N
     (e.g. top 20), and write them into `test-timing.json`'s `slowest` array
     instead of `[]`.
  2. If a JUnit dependency is undesirable, alternatively parse pytest's
     `--durations=N` textual output captured from the run into the same structure.
  3. Confirm `check_test_budget.py` consumes the `slowest` entries with the field
     names it already expects (read the iteration at ~lines 57–65 and match the
     keys; adjust the producer to those keys — do **not** loosen the gate logic).
  After this, a genuinely slow non-`@slow` test would actually trip
  `SLOW_TEST_FAIL_S` at the live gate. Keep `check_test_budget.py`'s existing
  thresholds and structure; only ensure it now receives real data.
- **Verification:** `test-timing.json` produced by `run_timed.sh` contains a
  non-empty `slowest` array with real durations; `check_test_budget.py` iterates it.

### 3.3 — `#12` CI jobs are sequential, ADR claims parallel (major)

- **Files:** `.github/workflows/ci.yml`, `docs/adr/0004-testing-foundation.md`
- **Problem:** Spec 04 §5.5 says "Jobs run in parallel; the workflow fails if any
  tier fails." But `ci.yml` chains jobs strictly via `needs:`: `lint` → `typecheck`
  (`needs: lint`, ~line 49) → `unit` (`needs: typecheck`, ~line 74) → `integration`
  (`needs: unit`, ~line 104) → `e2e` (`needs: integration`, ~line 144). ADR 0004
  (~lines 67–69) falsely documents "three **parallel** jobs — backend, frontend,
  e2e".
- **Fix (choose the lower-risk faithful option):** Prefer to **make the docs match
  reality** while improving real parallelism where safe:
  - At minimum, **correct ADR 0004** (~lines 67–69) to describe the actual
    ordered/staged pipeline (lint → typecheck → unit → integration → e2e, with the
    budget gate gating on the test stages) rather than "three parallel jobs".
  - Where independent, **decouple** stages that need not be sequential so they run
    in parallel: e.g. `lint` and `typecheck` can run independently; `unit` and
    `integration` can each depend only on `typecheck` rather than chaining
    `integration → unit`. Keep the budget-gate job depending on the test jobs it
    measures, and keep `e2e` after the build it needs. Only relax a `needs:` edge
    when the downstream job does not actually require the upstream artifact.
  Whatever the final graph, ADR 0004's description must match `ci.yml` exactly.
- **Verification:** ADR 0004 wording matches the `needs:` graph in `ci.yml`; no
  `needs:` edge claims a dependency that does not exist.

### 3.4 — `#14` ADR 0004 baseline outdated (nit)

- **File:** `docs/adr/0004-testing-foundation.md`
- **Problem:** The "Measured baseline" table records `37 | ~3 s` (accurate at spec
  04 completion). The suite has since grown to ~759 tests. The ADR does not note the
  figure is point-in-time, nor cross-reference ADR 0053 (spec 53), where the current
  xdist strategy and counts live.
- **Fix:** Add a short note under/next to the baseline table stating it is a
  **point-in-time spec-04 baseline** (37 tests) and that the **current** suite size,
  timings, and xdist strategy are tracked in **ADR 0053** (cross-reference it). Do
  not delete the historical figure — annotate it.

### 3.5 — `#92` spec-25 refactor doc claims a budget met only under xdist (minor)

- **Files:** `docs/refactors/25-compilation.md`, `backend/pyproject.toml`,
  `justfile`
- **Problem:** The compilation-refactor changelog claims ~51 s, but that number was
  measured with `run_timed.sh` (`-n auto`); the default single-threaded run is ~3 m
  01 s. The behavioural fix is the shared `-n auto` change in §3.1.
- **Fix:** The code fix is covered by §3.1 (no separate code change here). In
  `docs/refactors/25-compilation.md`, add a one-line clarification that the
  reported timing is measured under the xdist budget path
  (`just test-timed` / `run_timed.sh`, `-n auto`), which is now also the default and
  CI path after fix §3.1. Keep the historical number; just disambiguate how it is
  measured.

### 3.6 — `#2` ruff `extend-exclude` wording (nit)

- **File:** `backend/pyproject.toml`
- **Problem:** Spec 01 §5.2 says "Exclude `migrations/`", implying a plain `exclude`
  key; the implementation uses `extend-exclude = ["migrations"]` (~line 63).
  `extend-exclude` is actually safer (preserves ruff's built-in default excludes),
  but it deviates from the literal spec wording.
- **Fix:** Keep `extend-exclude` (it is the better choice) and add a short inline
  comment on that line explaining the deliberate use of `extend-exclude` over a
  plain `exclude` (preserves ruff's built-in default excludes). No behavioural
  change.

## 4. Acceptance criteria

1. **`#221`/`#239`/CI:** `.github/workflows/ci.yml` passes `-n auto` to **both** the
   unit and integration pytest invocations.
2. **`#8`/`#11`/`#10`/`#107`/default:** `just test` runs with xdist (via `addopts`
   or the recipe), and `pyproject.toml`'s "CI adds `-n auto`" comment is now true or
   removed.
3. **Budget:** `just test-timed` completes **green in < 120 s**, and the budget gate
   measures parallel wall-clock.
4. **`#231`/`#223`:** `run_timed.sh` (and the CI budget step) emit a **non-empty**
   `slowest` array of real per-test durations into `test-timing.json`;
   `check_test_budget.py` iterates real data (a slow non-`@slow` test could trip
   `SLOW_TEST_FAIL_S`). No more hardcoded `"slowest": []`.
5. **`#12`:** ADR 0004's job-topology description matches the actual `needs:` graph
   in `ci.yml`; no claimed dependency is false.
6. **`#14`:** ADR 0004 marks the 37-test baseline as point-in-time and
   cross-references ADR 0053.
7. **`#92`:** `docs/refactors/25-compilation.md` clarifies its timing is measured
   under the xdist budget path (now the default/CI path too).
8. **`#2`:** `pyproject.toml` carries an inline comment justifying `extend-exclude`.
9. The full suite is green and **< 2 minutes** under `just test-timed`.

## 5. Test plan

> This pack mostly edits infra/docs, not test source. Do not add backend test
> files here (they belong to other packs). Verify via the existing gate.

- **Stay green:** `backend/scripts/check_test_budget.py`'s own unit tests
  (e.g. the performance/budget tests that inject mock `slowest` data) must still
  pass — keep the field names the producer writes consistent with what the gate
  reads, so those tests are unaffected.
- **Updated tooling proves each fix:**
  - Run `just test-timed` and confirm: exits 0, total wall-clock < 120 s, and
    `test-timing.json` now has a populated `slowest` array.
  - `grep -n 'n auto' .github/workflows/ci.yml` shows it on the unit and integration
    steps.
  - Manually confirm the ADR 0004 wording matches the `ci.yml` `needs:` graph.
- **Performance/budget note:** The headline change *is* the budget fix — enabling
  xdist on the default/CI path brings the ~3 m single-threaded run under the
  2-minute budget. Do not add slow tests; do not disable xdist.

## 6. Definition of Done

- [ ] All 13 issues in §3 fixed (the `-n auto` root fix applied once in CI,
      `pyproject.toml`, and `justfile`; slow-test detector fed real data; ADR/docs
      corrected; ruff comment added).
- [ ] All acceptance criteria in §4 pass.
- [ ] `just test-timed` is green and **< 2 minutes**, with a non-empty `slowest`
      array in `test-timing.json`.
- [ ] Edits limited to the files in §2 — no out-of-scope files touched.
- [ ] No Overleaf code copied; stack unchanged.
