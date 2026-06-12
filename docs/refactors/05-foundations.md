# Refactor 05 — Foundations (specs 01–04)

First refactoring pass. **No features, no public-contract changes.** A
judgement-applied cleanup over the foundation code with the suite kept green and
under budget throughout.

## Scope & method

Surface reviewed: `backend/src/inkstave/**`, `backend/tests/**`,
`backend/migrations/**`, `backend/pyproject.toml`, `docker-compose.yml`,
`.env.example`, `justfile`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
the `frontend/` Vitest/Playwright scaffold, and `docs/adr/**`.

Tooling run as part of analysis:

- `ruff check` (current config) — clean; plus an **ad-hoc** extended run
  (`RUF,SIM,C4,PTH,RET,PIE,PERF,A,T20,TRY,EM,N`) to surface latent smells.
- `ruff format --check` — clean.
- `mypy --strict` and `mypy --warn-unreachable` — clean (no dead code).
- `pytest --cov` with branch coverage — to find untested branches.
- `pip-audit` against the resolved runtime deps — **no known vulnerabilities**.
- Secrets scan (grep for secret/password/key/token literals) — none in `src`.
- Confirmed `.env` is git-ignored and **not tracked**.

## Findings catalogue

| id | area | category | severity | effort | risk_of_fix | decision | rationale |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F-001 | `app.py` lifespan | bug | low | low | low | **applied** | Redis pool leaked if DB wiring raised during startup; wrapped startup in try/finally so the pool is always disposed. |
| F-002 | `app.py` lifespan | missing-test | med | low | low | **applied** | Lifespan open/dispose path was uncovered; added integration test (fake Redis + real test DB) incl. dispose-on-failure guard for F-001. |
| F-003 | `db/session.py` | missing-test | med | low | low | **applied** | The real `get_db_session` was only exercised via a copied override; added tests driving the real dependency's commit/rollback/unavailable paths. |
| F-004 | `db/engine.py` | missing-test | low | low | low | **applied** | `create_engine_and_sessionmaker` (incl. the missing-DSN `ValueError`) was uncovered; added a unit test. |
| F-005 | `dependencies.py` | missing-test | low | low | low | **applied** | `get_redis` present/missing paths uncovered; added a unit test. |
| F-006 | `exception_handlers.py` | missing-test | med | low | low | **applied** | The `DEBUG` branch (appends exception class to the 500 message) is security-relevant and was untested; added a test asserting the class name appears but the raised message text still never leaks. |
| F-007 | `config.py` | missing-test | low | low | low | **applied** | Empty `CORS_ORIGINS` → `[]` branch was uncovered; added a unit test. |
| F-008 | exceptions (`session.py`, `dependencies.py`) | smell | low | low | low | **skipped** | Ad-hoc `EM101`/`TRY003`/`TRY300` (string literal in `raise`, long message, `else`-after-`return`). Opinionated rules deliberately not enabled; the messages are short and idiomatic. Enabling them would add boilerplate locals for no real gain. |
| F-009 | `app.py` CORS | security | low | med | med | **skipped** | `allow_methods/headers=["*"]` with `allow_credentials=True`. Origins are an explicit allowlist (not `*`), so Starlette echoes safely — not a vulnerability. Broader security-header hardening is owned by spec 52. |
| F-010 | backend `src` | dead-code | — | — | — | **none found** | `mypy --warn-unreachable` and `ruff` unused-symbol rules reported nothing. |
| F-011 | runtime deps | security | — | — | — | **none found** | `pip-audit` reported no known vulnerabilities. |
| F-012 | `main.py` | missing-test | low | low | low | **skipped** | The uvicorn entrypoint (`app = create_app()`) is trivial and already exercised by the uvicorn smoke; a dedicated test adds noise, not value. |
| F-013 | `middleware.py` | missing-test | low | low | low | **skipped** | The non-HTTP scope passthrough (lines 34–35) only matters for WebSockets/lifespan scopes, which arrive with the realtime specs (28+). Deferred to when there is a real WebSocket to exercise it. |
| F-014 | repo root | security | low | low | low | **no action** | Confirmed `.env` is git-ignored and not tracked; no hard-coded secrets in `src`. |

## Applied fixes — before/after

- **F-001** (`app.py`): the lifespan previously created the Redis pool, then
  built the DB engine **outside** the `try`/`finally`. If engine creation
  raised, the pool was never closed. *After:* the Redis pool and DB wiring run
  inside a single `try`, and the `finally` disposes whatever was created. External
  startup behaviour is unchanged (a failure still propagates and aborts startup);
  only resource cleanup improved. Verified by
  `test_lifespan_disposes_redis_when_db_wiring_fails`.
- **F-002…F-007** (tests only): added 11 tests across `tests/unit/test_engine.py`,
  `tests/unit/test_dependencies.py`, `tests/unit/test_config.py`,
  `tests/integration/test_session_dependency.py`,
  `tests/integration/test_lifespan.py`, and `tests/integration/test_app.py`.
  No production code changed for these.

Commits: changes live in the working tree (this project has not been committed
to git history yet; the loop applies specs sequentially without per-spec
commits). Each fix was applied and the full suite re-run green before moving on.

## Behaviour unchanged — verification

- **Public contracts diffed:** API paths (`/health`, `/ready`,
  `/api/v1/openapi.json`), the error-envelope JSON shape, settings/env var
  names, and DB constraint names are **identical** to before. The OpenAPI
  document still exposes paths `['/health', '/ready']` and the
  `ErrorEnvelope`/`ErrorBody` components.
- **Migrations untouched:** no released Alembic migration was edited; no new
  migration was needed.
- **Suite green at each step**, and the existing 37 tests plus 11 new ones all
  pass.

## Measurements

| Metric | Before | After |
| --- | --- | --- |
| Backend tests | 37 | 48 |
| Backend coverage (branch) | 80.67% | 94.85% |
| Backend wall-clock | ~4.5 s | ~5.0 s |
| Frontend (Vitest) | 2 pass | 2 pass |
| E2E (Playwright) | 1 pass | 1 pass |
| `ruff` / `ruff format` / `mypy --strict` | clean | clean |

Total suite wall-clock remains a few seconds — far under the 2-minute budget.

## Net result

One real (if minor) robustness bug fixed (F-001) and a large, cheap
test-coverage gain (+14 pts, foundation now ~95% covered), with no behaviour or
contract change and the suite green and well under budget.
