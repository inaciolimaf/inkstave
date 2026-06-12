# Spec 05 — Refactor Foundations (requirements)

## 1. Summary

This is the first **refactoring spec**. It adds no features. It is a structured,
judgement-applied cleanup pass over everything produced by specs 01–04 (project
scaffolding, backend foundation, database foundation, testing foundation). The
deliverable is: a catalogue of findings (bugs, smells, dead code, missing tests,
performance and security issues), a risk-vs-value decision for each, the
**worthwhile fixes applied with tests staying green and no behaviour change**,
and a recorded changelog of what was applied versus deliberately skipped.

## 2. Context & dependencies

- **Depends on:** specs 01, 02, 03, 04 — all implemented with a **green, under-
  budget** suite (this is the safety net the refactor relies on).
- **Unlocks:** a cleaner, more trustworthy foundation for Phase 1 (auth) to
  build on; establishes the refactor-spec *process* reused at 10, 15, 20, …
- **Affected areas:** backend, infra, tests, docs (no frontend app exists yet
  beyond the Vitest scaffold; include it in scope).

## 3. Goals

- Run a systematic analysis over the 01–04 codebase covering, at minimum:
  - **Correctness/bugs:** lifespan resource leaks (engine/Redis pool not
    disposed on error paths), missing `await`s, broken transaction semantics in
    `get_db_session`, error-handler edge cases, request-id propagation gaps.
  - **Smells:** duplication, overlong functions, leaky abstractions, inconsistent
    naming, import-time side effects, settings reached outside DI.
  - **Dead code:** unused imports/symbols, unreachable branches, placeholder
    files no longer needed.
  - **Missing tests:** uncovered branches in error handling, `/ready` failure
    paths, DSN normalization, rollback isolation, lifespan dispose-on-failure.
  - **Performance:** anything that risks the < 2-minute budget (per-test schema
    recreation, accidental real network, missing fakes), inefficient fixtures.
  - **Security:** secrets logged or leaked in errors, tracebacks exposed,
    permissive CORS defaults, `.env` accidentally committed, unsafe defaults.
- For **each** finding: record severity, effort, risk, and a value judgement;
  decide **apply** or **skip** with a one-line rationale.
- Apply the worthwhile fixes in small, reversible commits, **keeping tests green
  at every commit** and **without changing public behaviour/contracts**.
- Strengthen tests where applying a fix or covering a real gap is cheap and
  valuable (adding tests is always in-scope for a refactor pass).
- Produce a **refactor changelog** documenting applied vs. skipped findings.

## 4. Non-goals (explicitly out of scope)

- New features, new endpoints, new env vars (beyond removing/renaming
  *unused* ones, which counts as a contract change and must be recorded).
- Large architectural rewrites; prefer minimal, safe edits over redesigns.
- Changing public contracts (API paths, error envelope shape, settings/env var
  names, DB constraint names, migration history) unless a finding makes a
  compelling, recorded case and tests are updated accordingly. **Released
  Alembic migrations are never edited** — add a new one if a schema fix is
  truly warranted (it likely is not at this stage).
- Anything depending on specs not yet implemented (auth, projects, compile, …).

## 5. Detailed requirements (process)

### 5.1 Analysis pass

- Enumerate the surface to review: `backend/src/inkstave/**`, `backend/tests/**`,
  `backend/migrations/**`, `backend/pyproject.toml`, root `docker-compose.yml`,
  `.env.example`, `justfile`, `.pre-commit-config.yaml`, CI workflow,
  `frontend/` Vitest scaffold, and `docs/adr/**`.
- Use available tooling as part of analysis (do not rely on intuition alone):
  - `ruff check` (including rule sets not yet enabled, run ad-hoc) and
    `ruff format --check`.
  - `mypy --strict` and consider `--warn-unreachable` to surface dead code.
  - `pytest --cov` with branch coverage to find untested branches.
  - `pip-audit`/`uv`'s audit (or equivalent) for dependency vulnerabilities, and
    a secrets scan (e.g. grep for obvious secret patterns; confirm `.env` is
    git-ignored and not tracked).
  - A dead-code check (e.g. `vulture` or `ruff` unused-symbol rules) — advisory.
- Optionally spawn parallel sub-analyses by concern (correctness / smells /
  tests / perf / security) and merge their findings into one catalogue.

### 5.2 Findings catalogue (required artifact)

Maintain a table (in the changelog doc, see §5.4). Each row:

| Field | Meaning |
| --- | --- |
| `id` | stable identifier (e.g. `F-001`) |
| `area` | file/module/path |
| `category` | bug / smell / dead-code / missing-test / perf / security |
| `severity` | low / medium / high |
| `effort` | low / medium / high |
| `risk_of_fix` | low / medium / high (regression risk) |
| `decision` | applied / skipped |
| `rationale` | one line justifying the decision |
| `commit` | short SHA / link if applied |

### 5.3 Decision rule (risk vs. value)

- **Apply** when value (correctness/security/clarity/test-coverage gain) clearly
  exceeds risk and effort, and the change is local and reversible with tests
  proving it.
- **Skip** when the fix is speculative, risks regressions disproportionate to
  the gain, expands scope, or would touch a public contract without strong
  justification. Skipping is a valid, recorded outcome.
- Bias toward **small, safe** changes. Group trivially-safe edits (formatting,
  unused-import removal) into a single commit.

### 5.4 Refactor changelog (required deliverable)

- Write `docs/refactors/05-foundations.md` containing:
  - A short summary of scope and method.
  - The full findings catalogue table (§5.2).
  - For each **applied** finding: before/after note and the commit reference.
  - For each **skipped** finding: the reason.
  - A "behaviour unchanged" statement and how it was verified (suite green;
    public contracts unchanged; OpenAPI schema diff empty or explained).

### 5.5 Configuration

- No new env vars expected. If a finding *removes* an unused var, update
  `.env.example` and record it as a contract change in the changelog.
- No new runtime dependencies. Dev-only analysis tools (vulture, pip-audit) may
  be added to the `dev` group if they are used by the process; remove them again
  if they are one-off, or keep and wire into CI only if cheap.

## 6. Overleaf reference (study only — never copy)

**None.** This is a process pass over Inkstave's own foundation code. Overleaf
has no equivalent "refactor spec" to study. The originality rule still applies:
Overleaf may be read for understanding, but nothing is copied, and no specific
Overleaf path is relevant here.

## 7. Acceptance criteria

1. **Given** the start of this spec, **when** I run the full suite, **then** it
   is green and under 2 minutes (precondition verified and recorded).
2. **Given** the analysis pass, **when** it completes, **then**
   `docs/refactors/05-foundations.md` exists and contains a findings catalogue
   with at least the columns in §5.2, and every finding has a recorded
   `decision` + `rationale`.
3. **Given** each **applied** fix, **when** its commit lands, **then** the full
   suite is green at that commit (no commit leaves the suite red).
4. **Given** the completed refactor, **when** I diff public contracts (API
   paths, error envelope JSON shape, settings/env var names, DB constraint
   names, the OpenAPI document), **then** there is **no change** — or every
   change is explicitly listed and justified in the changelog as a deliberate
   contract change with tests updated.
5. **Given** the completed refactor, **when** I run `ruff check`,
   `ruff format --check`, and `mypy --strict` on the backend, **then** all pass
   with no findings.
6. **Given** the completed refactor, **when** I run the full suite, **then** it
   is green and total wall-clock is still **under 2 minutes**.
7. **Given** the security review portion, **when** I check the repo, **then**
   `.env` is not tracked, no secret is hard-coded or logged, tracebacks are not
   exposed in error responses, and any finding here is applied or has a recorded
   skip rationale.
8. **Given** the changelog, **when** I read it, **then** it clearly separates
   **applied** vs **skipped** findings and asserts "no behaviour change" with the
   verification method.

## 8. Test plan

> No new feature tests. The existing suite is the safety net; it must stay green
> and under budget throughout. Tests are *added* only to close real coverage
> gaps surfaced by the analysis.

- **Unit / Integration (pytest):** the existing 01–04 tests must remain green at
  every commit. Add targeted tests for any genuine uncovered branch a fix
  touches (e.g. lifespan dispose-on-error, `/ready` failure paths, DSN
  normalization, rollback isolation) — only where cheap and valuable.
- **Frontend (Vitest):** the sample test must remain green; add a test only if a
  real gap in the scaffold is found.
- **E2E (Playwright):** the smoke spec must remain green; unchanged unless a
  finding requires it.
- **Regression guard:** capture the OpenAPI document (and, if practical, a
  snapshot of the error-envelope responses) before and after; assert they are
  identical to prove "no behaviour change", or document any intended diff.
- **Performance/budget note:** measure suite wall-clock before and after; record
  both in the changelog. Any fix that would slow the suite is rejected or
  redesigned. No real LaTeX/LLM/network is introduced.

## 9. Definition of Done

- [ ] Analysis pass completed across specs 01–04's output; findings catalogued.
- [ ] Each finding has a risk-vs-value `decision` (applied/skipped) + rationale.
- [ ] Worthwhile fixes applied in small commits; suite green at every commit.
- [ ] No behaviour/contract change (or every deliberate change recorded and
      tests updated); OpenAPI/error-envelope diff verified.
- [ ] Full suite green and **< 2 minutes** (before/after timings recorded).
- [ ] `ruff`/`ruff format`/`mypy --strict` clean.
- [ ] `docs/refactors/05-foundations.md` written with applied-vs-skipped record.
- [ ] No Overleaf code copied.
