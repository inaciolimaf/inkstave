# Refactor 10 — Auth & Frontend Foundation (specs 06–09)

Phase-1 refactoring pass. **No features, no public-contract changes.** A
security-focused review of the auth backend (user model, hashing, tokens,
refresh store, guards, rate-limit groundwork, endpoints) and the frontend
foundation (api-client, token-store, auth-context, guards, pages).

## Method & precondition

- **Pre-refactor:** 06–09 tests confirmed green (backend 116 + frontend 31 +
  e2e), suite under budget.
- Tooling: `pytest --cov` (branch) on the auth modules, `ruff`/`mypy --strict`,
  `pnpm lint`/`typecheck`, plus targeted greps for secret/PII logging,
  `dangerouslySetInnerHTML`, and access-token-in-storage.

The auth surface was already built carefully (97% branch coverage, no plaintext
or hash logged, `jwt_secret` required with no default, uniform login errors,
DB-authoritative admin, fail-open limiter). The review found **no
behaviour-changing defects**; the worthwhile work was one defensive hardening
and closing the remaining security-relevant coverage gaps.

## Findings catalogue

| id | area | category | severity | decision | rationale / change |
| --- | --- | --- | --- | --- | --- |
| F-001 | `auth/password.py` | security/robustness | low | **applied** | `PasswordHasher.verify` now catches **any** exception and returns `False` (fail-closed). A password check must never raise, and a corrupted stored hash must never accidentally grant access. (`auth/password.py` verify). No observable contract change. |
| F-002 | `auth/tokens.py` | missing-test (security) | med | **applied** | The secret-rotation path (a token signed with a `jwt_secret_previous` entry must still verify; an unknown secret must not) was unasserted. Added `test_decode_accepts_a_previous_secret_during_rotation`. |
| F-003 | `services/auth.py` | missing-test (security) | med | **applied** | A refresh whose `sub` user was **deleted** must yield 401 (no token minted for a ghost account). Added `test_refresh_with_deleted_user_is_401`. |
| F-004 | `services/auth.py` | missing-test | low | **applied** | Idempotent logout on an **invalid** token (decode fails → still 200, leaks nothing) was uncovered. Added `test_logout_with_invalid_token_is_idempotent`. |
| F-005 | `auth/rate_limit.py` | missing-test | low | **applied** | The IP-only fallback when the request body is unparseable was uncovered. Added `test_identity_falls_back_to_ip_when_body_unparseable`. |
| F-006 | `auth/refresh_store.py` | missing-test | low | **applied** | `rotate_refresh` on a missing `jti` (no-op) was uncovered. Added `test_rotate_missing_jti_is_noop`. |
| F-007 | frontend `auth-context` | missing-test (security) | med | **applied** | "Logout clears local state even if the network call fails" was unasserted. Added `auth-context.test.tsx` proving tokens are cleared when `/auth/logout` rejects. |
| F-008 | `auth/rate_limit.py` | security | med | **deferred → spec 52** | The limiter trusts `X-Forwarded-For` unconditionally; without a trusted proxy in front, a client can spoof it to vary its identity and bypass per-IP limits. This is acceptable for the *groundwork* (the deployment is expected to terminate behind a trusted proxy); full proxy-trust hardening (a configurable trusted-hop count / `ProxyHeadersMiddleware`) is **owned by spec 52**. Documented, not changed, to avoid altering the spec-08 contract. |
| F-009 | `services/auth.py` refresh | robustness | low | **skipped** | `refresh_tokens` reads `claims["family_id"]` directly; a validly-signed refresh token without it would `KeyError` (→500). **Cannot occur**: only our token service mints refresh tokens and it always sets `family_id`; an attacker cannot forge a signature. Adding a `.get()` guard is dead-defensive; skipped to keep the code honest about its invariant. |
| F-010 | login timing (tests) | observation | low | **skipped (note)** | In *tests*, argon2 cost is lowered for real hashes but the constant `_DUMMY_HASH` carries default params, so the missing-user path is *slower* than the wrong-password path. This is a test-only artifact — in production both use default cost, giving the intended timing parity. No code change. |

## §5.3 Security checklist

1. **Argon2id, settings-driven cost; no hash/plaintext logged** — **PASS** (grep
   confirms no secret/token/password logging; cost from settings; tested).
2. **Login uniform error + dummy-hash compare (no enumeration)** — **PASS**
   (`test_login_failures_are_uniform`; dummy-hash compare in `authenticate_user`).
3. **JWT secret required; HS256; type+exp+signature verified** — **PASS**
   (`jwt_secret: str` no default; `decode_token` checks signature/exp/iss/type;
   wrong-type/bad-sig/expired all tested).
4. **Refresh rotation + reuse detection + family revocation; revoked ⇒ no usable
   access** — **PASS** (`test_refresh_reuse_revokes_family`,
   `test_revoked_family_cannot_mint_access`).
5. **Guards: 401/403, `WWW-Authenticate`, admin DB-authoritative** — **PASS**
   (`test_me_without_token_is_401_with_challenge`,
   `test_admin_check_is_db_authoritative`).
6. **Rate limiter fail-open, correct keying, `Retry-After`, no easy bypass** —
   **PASS** with a **deferred** caveat (F-008: proxy-header trust → spec 52).
   Fail-open, keying, and `Retry-After` are tested.
7. **No secrets/tokens/PII in logs or error bodies** — **PASS** (grep clean;
   tracebacks logged but never returned; `UserPublic` excludes the hash).
8. **Frontend access token in memory only; one-shot deduped refresh; no token in
   URLs/logs; logout always clears** — **PASS / FIXED** (token-store tests;
   api-client dedupe/one-shot tests; F-007 logout-on-failure test added).
9. **No `dangerouslySetInnerHTML` / XSS sink in auth UI** — **PASS** (grep clean;
   React escapes; error content rendered as text).
10. **Migration up/down correct; no released migration edited** — **PASS** (spec
    06 verified `citext` + `uq_users_email` + downgrade; no migration touched
    here).

## Behaviour unchanged — verification

- The complete 06–09 test set still passes **unmodified** (no existing test was
  changed for being wrong). The only production change (F-001) makes `verify`
  catch a strictly larger set of errors as "not a match" — the observable
  contract (correct password → True, anything else → False) is identical.
- Public contracts (paths, status codes, error envelope, token claims/semantics)
  are untouched; OpenAPI paths and the error envelope are unchanged.

## Measurements

| Metric | Before | After |
| --- | --- | --- |
| Backend tests | 116 | 121 |
| Auth-module branch coverage | ~95–97% | **100%** (all of `auth/*`, `services/auth`) |
| Backend wall-clock | ~4 s | ~3.6 s |
| Frontend Vitest | 31 | 32 |
| E2E (Playwright) | 1 pass | 1 pass |
| `ruff`/`mypy` (backend), `lint`/`typecheck` (frontend) | clean | clean |

Suite remains well under the 2-minute budget.

## Net result

No behaviour-changing bugs were found — the auth foundation was sound. One
fail-closed hardening (F-001) and six security-relevant tests (F-002…F-007)
were applied, lifting every auth module to 100% branch coverage. One real
weakness (F-008, proxy-header trust) is documented and deferred to spec 52,
which owns rate-limit hardening.
