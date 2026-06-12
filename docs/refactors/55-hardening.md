# Refactor 55 — Hardening pass (specs 51–54)

A scan → evaluate → apply pass over the Phase-7 hardening surface (observability,
security, performance/test-speed, e2e). No new features. Every applied fix has a
regression test; every security and flakiness fix has a dedicated one. Suite stays
green and well under the 2-minute budget.

## Scan summary

Three parallel read-only audits covered the §5.1 checklist (observability,
security, test-speed/flakiness/e2e). Most items were **verified correct** (context
reset in the HTTP/WS middleware, gauge cleanup, probe exclusion, readiness honesty,
OTEL no-op; rate-limit coverage on routes, CORS/secret/JWT boot guards, upload
mid-stream caps + sniffing + filename sanitisation, error hygiene, compile sandbox;
template-DB isolation, external guards, budget gate). The defects below were found
and fixed.

## Applied changes

| # | Spec | Defect | Fix (files) | Regression test |
|---|------|--------|-------------|-----------------|
| 1 | 51 | `s3_access_key_id` not redacted — `"access_key_id"` didn't match the `"api_key"` denylist entry, so the S3 secret could leak to logs | added `"access_key"` to the secret-substring denylist (`observability/log.py`) | `test_hardening_55::test_secret_access_key_is_redacted` |
| 2 | 51 | The agent ARQ job (`run_agent_turn`) never bound correlation context nor cleared it, and the agent enqueuer didn't chain `request_id` — agent logs were uncorrelated and prior-job context could persist | thin wrapper binds `request_id/job_id/trace_id` and **always** clears in `finally`; enqueuer chains `request_id` (`agent/api/jobs.py`, `agent/api/enqueuer.py`) | `test_hardening_55::test_agent_job_binds_and_clears_context` |
| 3 | 52 | Auth limiter `INCR` then `EXPIRE` was **non-atomic** (a counter could be left without a TTL → permanent lock-out on a crash) | atomic Lua `INCR+EXPIRE` with a `ResponseError` fallback, mirroring `security.rate_limit` (`auth/rate_limit.py`) | `test_hardening_55::test_auth_limiter_sets_ttl_on_first_hit` |
| 4 | 52 | `client_ip` trusted `X-Forwarded-For` **unconditionally** — an attacker could spoof the header to dodge the per-IP auth limit | honour the proxy header only when `trust_proxy_headers` is set; single source of truth shared by both limiters (`auth/rate_limit.py`) | `test_rate_limit::test_client_ip_uses_proxy_header_only_when_trusted` (corrected a test that asserted the insecure behaviour) |
| 5 | 52 | 16 request **body** models extended bare `BaseModel` — unknown fields were silently accepted (request smuggling) | switched all to `StrictModel` (`extra="forbid"`): auth/user/project/tree/sharing/compile/history schemas | `test_hardening_55::{test_request_models_forbid_extra_fields, test_unknown_request_field_is_rejected}` |
| 6 | 52 | No automated audit that every sensitive route is rate-limited | `__rate_limit__` marker on the limiter dependencies + a guard-coverage test (analogous to the spec-34 authz check), plus a headers-on-error test | `test_hardening_55::{test_every_sensitive_route_is_rate_limited, test_security_headers_present_on_error_responses}` |
| 7 | 53/54 | **Flaky teardown** (`test_collab_manager` — asyncpg `connection is closed`) under high `-n auto`: the manager's debounced flush/evict `asyncio.Task`s woke up against the per-test connection after it was closed/rolled-back | `DocumentManager.aclose()` cancels all background tasks; called in the app lifespan before engine dispose; the test harness uses large debounces (no spontaneous firing) + an autouse fixture that `aclose()`s managers before the connection closes (`collab/manager.py`, `app.py`, `tests/integration/test_collab_manager.py`) | `test_collab_manager::test_aclose_cancels_pending_background_tasks` + full `-n auto` green ×2 |
| 8 | 54 | **Flaky e2e** under parallel load: the single shared backend + ARQ worker saturated, stalling collab WS sync and async agent/compile jobs past the 10s wait | capped default Playwright workers to 2 (`E2E_PLAYWRIGHT_WORKERS` overrides) and gave the genuinely-async collab-sync waits a 20s budget via an `EditorPage.waitEditable()` helper (`frontend/playwright.config.ts`, `frontend/e2e/`) | the de-flaked specs run reliably (see runtimes) — real contention reduction, not blanket retries |

## Deliberately skipped / deferred

- **Backend mypy debt (17 pre-existing errors)** — unused `type: ignore` / missing
  type-args in files unrelated to 51–54 (`graph.py`, `runner.py`, `project.py`,
  `config.py`, `tree.py`, `security/rate_limit.py:66`, …). Out of scope (not the
  hardening surface) and cleaning them risks regressions across stub versions.
  This pass is **mypy-neutral** (total stays at 17; my changed files add zero new
  errors). *Defer to a dedicated typing cleanup.*
- **E2E presence rendering** (a late-joining context doesn't reliably receive a
  peer's awareness frames, though document sync propagates both ways) — a collab
  **feature** issue (specs 28–32), not part of the 51–54 hardening surface. Already
  documented in `docs/e2e-strategy.md`. *Defer to a collaboration-focused pass.*
- **`security/rate_limit.py` belt-and-suspenders proxy gate** — now redundant since
  `client_ip` gates internally, but kept (still correct) to avoid churn/risk.

## Acceptance-criterion corrections

- `test_rate_limit::test_client_ip_prefers_trusted_proxy_header` asserted the
  **insecure** behaviour (always trusting `X-Forwarded-For`). Rewritten as
  `test_client_ip_uses_proxy_header_only_when_trusted` to assert the secure rule
  (header honoured only when `trust_proxy_headers`).

## Runtime (before → after)

| Tier | Before | After |
|------|--------|-------|
| Backend `pytest -n auto` | ~19–23 s (intermittently red on the teardown race) | **~32 s, reliably green ×2** |
| Backend `-n 4` | ~22 s | ~22 s |
| Backend single-threaded (`just test`, no xdist) | ~3 m 01 s | ~3 m 01 s (unchanged) |
| Frontend Vitest | ~10.5 s | ~10.5 s (unchanged) |
| E2E smoke (Playwright) | ~18–37 s, intermittently red under 6 workers | **~31–40 s at 2 workers, green across repeated runs** |
| **Total** | — | **well under the 120 s budget (under xdist)** |

> **Budget caveat (AC6).** The single-threaded default (`just test`, no `-n`) runs
> the backend serially at **~3 m 01 s**, which *exceeds* the 2-minute budget. The
> 2-minute budget is measured **under xdist** (`pytest -n auto`); the parallel run is
> the canonical timing. Run the suite with `-n auto` to stay within budget.

## De-flaked / stabilised tests

- `tests/integration/test_collab_manager.py` — all, especially
  `test_bridge_write_does_not_create_crdt_update` (the asyncpg teardown race under
  `-n auto`). Root-caused via `DocumentManager.aclose()` + explicit-flush test
  harness, not by adding sleeps or retries.
- E2E `editor.spec` / `agent.spec` / `collab.spec` — stabilised by reducing
  single-backend contention (2 workers) and giving collab-sync waits a real budget.

## Reference updates

- `docs/security-checklist.md` — noted the atomic limiter, the proxy-header gate,
  and `extra="forbid"` on every request model.
- No data-model changes, no migrations, no new/removed env vars (the existing
  `E2E_PLAYWRIGHT_WORKERS` now has a documented default of 2).
