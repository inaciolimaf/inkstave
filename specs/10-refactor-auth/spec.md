# Spec 10 — Refactor: Auth & Frontend Foundation (requirements)

## 1. Summary

This is the Phase-1 **refactoring** spec. It adds no features. Automated agents
review everything built in specs **06–09** (user model & registration, JWT auth,
guards & rate-limit groundwork, frontend foundation) for bugs, smells, security
issues and missing tests; evaluate each finding by risk vs. value; apply the
worthwhile fixes while keeping all tests green and the public behaviour
unchanged; and record what was applied and what was deliberately skipped.

## 2. Context & dependencies

- **Depends on:** specs **06, 07, 08, 09** — all implemented, tests green.
- **Unlocks:** a clean, secure auth base for Phase 2 (projects/files) to build on.
- **Affected areas:** backend auth surface, frontend foundation, tests, docs
  (changelog + any ADR updates). No schema changes unless a defect requires one
  (then ship a new Alembic migration; never edit a released one).

## 3. Goals

- Find and fix real defects and security weaknesses in the auth + frontend
  foundation **without changing externally observable behaviour**.
- Raise test coverage on the security-critical paths (hashing, token
  verification, rotation/reuse, guards, refresh-on-401).
- Improve readability/consistency (naming, error handling, typing, dead-code
  removal, DRYing duplicated logic) where low-risk.
- Produce an auditable record (applied vs. skipped) and a completed security
  checklist.

## 4. Non-goals (explicitly out of scope)

- New features, endpoints, pages, or contract changes.
- Production rate-limiting hardening beyond fixing defects in the existing
  groundwork (spec 52 owns full hardening).
- Refactoring Phase-0 foundations (01–05) unless a fix is trivially local and
  justified in the changelog.
- Large architectural rewrites; prefer minimal, reversible changes.

## 5. Detailed requirements

### 5.1 Process

1. **Inventory the surface.** Enumerate the auth backend modules (User model &
   migration, password hashing, token service, refresh store, guards/
   dependencies, rate-limit dependency, auth/users routers, schemas) and the
   frontend foundation (api-client, token-store, auth-context, RequireAuth, login/
   register/home pages, config).
2. **Scan for findings** across these categories (non-exhaustive — see §5.2):
   correctness bugs, security issues, smells/duplication, missing/weak tests,
   typing gaps, error-handling inconsistencies, performance traps.
3. **Triage** each finding with: severity (low/med/high), risk-of-fix, value,
   and decision (apply / defer / skip) + rationale.
4. **Apply** worthwhile, low-risk fixes incrementally, running the test suite
   after each change so the suite never goes red.
5. **Add tests** to lock in any fixed bug and to cover any discovered gap,
   especially security-relevant cases.
6. **Document** results in a changelog under `docs/` (see §5.4) and complete the
   security checklist (§5.3).

### 5.2 What to look for (checklist of candidate findings)

**Backend — security & correctness:**

- Password hashing: argon2id actually used; cost params come from settings;
  `verify_password` never raises on malformed input; no plaintext or hash ever
  logged.
- Login enumeration: identical `401` message and comparable timing for unknown-
  email vs. wrong-password (dummy-hash compare present and effective).
- Token verification: signature, `exp`, **and** `type` all checked; an access
  token is rejected where a refresh is expected (and vice-versa); clock-skew not
  silently ignored; `JWT_SECRET` is required (no insecure default).
- Refresh rotation/reuse: old token invalidated on rotation; replay of a rotated
  token revokes the whole family; revoked families cannot mint usable access
  tokens; Redis TTLs set so tokens self-expire; key namespaces don't collide.
- Guards: `401` vs `403` used correctly; `WWW-Authenticate` header present on
  401; `require_admin` uses the DB row not just the claim; unknown-`sub` → 401
  (not 500); no information leakage in error bodies.
- Rate limiter: fail-open on Redis outage; correct key/identity; `Retry-After`
  set; no off-by-one in window logic; cannot be trivially bypassed.
- Secrets/PII: no secrets, tokens, or password material in logs or error
  responses; structured logs scrub sensitive fields.
- Input validation: email normalisation consistent everywhere it matters;
  72-char password cap enforced consistently; integrity-race path returns 409.
- Migration sanity: `citext` extension + unique constraint correct; downgrade
  works.

**Frontend — security & correctness:**

- Access token kept **in memory only**, never written to `localStorage`/
  `sessionStorage`; refresh-token storage matches the documented trade-off.
- Refresh-on-401: retries at most once; concurrent 401s share one refresh
  promise (no thundering herd / no infinite loop); refresh-failure clears auth
  and redirects.
- No token leakage into URLs, logs, or error toasts; `Authorization` header not
  attached to cross-origin third-party requests.
- Error handling: backend `422` field errors mapped to fields; generic `detail`
  surfaced safely; no XSS via unescaped error content (React escapes by default —
  verify no `dangerouslySetInnerHTML`).
- Logout clears state even if the network call fails.
- a11y/loading/error states present as specified.

**General:**

- Dead code, duplicated logic (e.g. repeated token-decode), inconsistent naming,
  missing types/`Any`, broad `except`, TODOs that hide bugs.
- Test gaps on any of the above.

### 5.3 Security checklist (must be reviewed and recorded)

Record PASS / FIXED / N/A with a note for each:

1. Argon2id with settings-driven cost; no hash/plaintext logged.
2. Login uniform error + dummy-hash compare (no enumeration via message/timing).
3. JWT secret required; HS256; `type`+`exp`+signature verified.
4. Refresh rotation + reuse detection + family revocation correct; revoked ⇒ no
   usable access token.
5. Guards: 401/403 semantics, `WWW-Authenticate`, admin DB-authoritative.
6. Rate limiter fail-open, correct keying, `Retry-After`, no easy bypass.
7. No secrets/tokens/PII in logs or error bodies.
8. Frontend access token in memory only; one-shot deduped refresh; no token in
   URLs/logs; logout always clears local state.
9. No `dangerouslySetInnerHTML` / XSS sink in auth UI.
10. Migration up/down correct; no released migration edited.

### 5.4 Deliverable: changelog

Add `docs/refactors/10-auth.md` (or the project's established refactor-log
location) containing:

- A table of findings: id, area, category, severity, decision (applied/deferred/
  skipped), rationale, and link to the change (commit/PR or file+lines).
- The completed §5.3 security checklist with notes.
- A short "behaviour unchanged" statement explaining how the public contracts of
  06–09 were preserved (and which tests prove it).

### 5.5 Configuration

No new env vars unless a fix requires one (justify in the changelog and add to
`.env.example`). Do not weaken any existing security default.

## 6. Overleaf reference (study only — never copy)

None. This is an internal refactor of Inkstave's own code; there is no Overleaf
equivalent to reference.

## 7. Acceptance criteria

1. **Given** the start of the spec, **when** all of 06–09's tests are run,
   **then** they are green before any change is made (verified and noted).
2. **Given** the scan, **when** it completes, **then** a findings list exists
   with each item triaged (severity + apply/defer/skip + rationale).
3. **Given** the applied fixes, **when** the full suite runs, **then** it is
   green and completes in < 2 minutes, with **no change to the public
   request/response contracts, status codes, or token semantics** of 06–09
   (the existing 06–09 tests still pass unmodified, except where a test was
   itself fixed for being wrong — such changes are listed in the changelog).
4. **Given** each fixed bug, **when** the suite runs, **then** there is a test
   that fails before the fix and passes after (regression lock-in).
5. **Given** the §5.3 security checklist, **when** the spec ends, **then** every
   item is marked PASS/FIXED/N/A with a note.
6. **Given** the changelog deliverable (§5.4), **when** reviewed, **then** it
   lists every applied and every deliberately-skipped finding with rationale.
7. **Given** any deferred finding, **when** recorded, **then** it states why it
   was not worth applying now and (if relevant) which later spec should own it.

## 8. Test plan

> Keep the suite < 2 minutes. Refactors must not slow tests; if a new test is
> slow, mock the slow part (argon2 cost low; fake Redis; crafted-`exp` tokens).

- **Regression lock-in (pytest / Vitest):** for each fixed defect, a test that
  reproduces it (red before, green after).
- **Security tests (pytest):** strengthen coverage on hashing, token type/exp/
  signature rejection, rotation/reuse/family-revocation, guard 401/403, rate-
  limit fail-open, and "no secret in logs" assertions where feasible.
- **Frontend (Vitest):** assert access token never persisted to storage; refresh
  dedupe/one-shot; logout-clears-on-network-failure.
- **Full suite:** run everything from 06–09 plus the new tests; confirm green and
  within budget.
- **Performance/budget note:** no new slow paths introduced; verify total suite
  wall-clock stays under 2 minutes after changes.

## 9. Definition of Done

- [ ] Pre-refactor: 06–09 tests confirmed green.
- [ ] Findings scanned, triaged (apply/defer/skip with rationale).
- [ ] Worthwhile fixes applied; **no public-contract/behaviour change**.
- [ ] Each fixed bug has a regression test (red→green).
- [ ] §5.3 security checklist completed (PASS/FIXED/N/A + notes).
- [ ] Changelog (§5.4) written under `docs/`.
- [ ] Full suite green and < 2 minutes; lint/format/type-check clean (backend &
      frontend).
- [ ] No new tech/deps unless justified; any new env var documented.
- [ ] No Overleaf code copied.
