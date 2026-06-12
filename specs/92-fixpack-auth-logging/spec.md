# Spec 92 — Fix-Pack: Auth Logging & Exception Visibility (requirements)

## 1. Summary

This fix-pack resolves **4 confirmed observability issues** in the authentication
subsystem. Today the entire auth flow (`authenticate_user`, `login`,
`refresh_tokens`, `logout`) emits **zero** logs, user registration emits none,
the collab WebSocket auth path swallows its error with a bare `except Exception`,
and the rate-limit identity helper silently falls back to an empty email when a
request body can't be parsed. The result is that security-relevant events —
failed logins, **refresh-token reuse / family invalidation** (a session-compromise
signal), token rotation, duplicate-email conflicts, and WS auth rejections —
leave no trace. This pack adds structured logging at the right levels and narrows
the one over-broad catch.

The work is **observability-only**: no control-flow, status code, close code, or
error-message change. The **overriding constraint** is that no log record may ever
contain a password, a raw access/refresh token, or a token `jti`/family secret —
only `user_id` and the event name. Failed credentials are logged **without** the
attempted email or password.

**Severity breakdown:**
- major: 1 (`#A1` — auth flow has zero logging; reuse/invalidation passes silently)
- minor: 2 (`#A3` WS auth swallows its exception with no log; `#A2` registration
  has no logging)
- nit: 1 (`#A4` rate-limit body-parse fallback is invisible)

## 2. Files in scope

Edit **only** these files. If a fix appears to require another file, stop and
report.

```
backend/src/inkstave/services/auth.py
backend/src/inkstave/services/user.py
backend/src/inkstave/auth/rate_limit.py
backend/src/inkstave/collab/ws/router.py
backend/tests/unit/                  (new/updated unit test files may be added here)
```

> **Logging style to match** (already used across the codebase): a module-level
> `logger = logging.getLogger(__name__)`, then `logger.info(...)` /
> `logger.warning(...)` with **%-style positional args** and/or `extra={...}`.
> See `agent/llm/openrouter.py` (`logger.exception("openrouter complete failed")`),
> `cache.py` (`logger.warning("cache get failed (%s): %s", key, exc)`), and
> `exception_handlers.py`. Do **not** use f-strings inside the log call.

## 3. Issues to fix

### 3.1 — `#A1` Auth flow has ZERO logging (major · spec 06/52)

- **File:** `backend/src/inkstave/services/auth.py` (lines ~49–130)
- **Problem:** `authenticate_user`, `login`, `refresh_tokens`, and `logout` emit
  **no logs whatsoever**. Failed credentials, **refresh-token reuse → family
  revocation** (`record.rotated` branch, ~lines 102–105 — a compromise signal),
  family/user revocation rejections, successful logins, logouts, and token
  rotations all pass completely silently. There is no way to detect a
  credential-stuffing run or a stolen-token replay from the logs.
- **Fix:** Add a module logger (`logger = logging.getLogger(__name__)`) and emit:
  - **WARNING** on authentication failure: in `login`, when `authenticate_user`
    returns `None` (just before `raise InvalidCredentialsError()`). Log the
    **event only** — do **not** log the attempted email or password. Example:
    `logger.warning("auth login failed: invalid credentials")`.
  - **WARNING** on detected **refresh-token reuse** (the `record.rotated` branch,
    just before `revoke_family` / `raise RefreshError(_REUSE_DETECTED)`): this is
    the high-value signal. Include `user_id` (available as `record.user_id` /
    `claims["sub"]`) via `extra={"user_id": ...}` or a `%s` arg — **never** the
    `jti`, `family_id` value, or the raw token. Example:
    `logger.warning("refresh token reuse detected; revoking family", extra={"user_id": record.user_id})`.
  - **WARNING** on the other refresh rejections (`record is None` /
    family-revoked / user-revoked / unknown user) — a single warning per path is
    enough; again `user_id` only where available, never the token.
  - **INFO** on **successful login** (after `store_refresh`, in `login`):
    `logger.info("auth login ok", extra={"user_id": user.id})`.
  - **INFO** on **successful refresh rotation** (after the new token is stored, in
    `refresh_tokens`): `logger.info("auth refresh rotated", extra={"user_id": user.id})`.
  - **INFO** on **logout** (in `logout`, after `revoke_family`, when a valid token
    was decoded): `logger.info("auth logout", extra={"user_id": claims["sub"]})`.
    Note `logout` returns early on an undecodable token — that early-return path
    needs no log (or a DEBUG at most).
- **CRITICAL CONSTRAINT (restate):** the log calls must reference **only**
  `user_id` and the event string. **Never** pass `data.password`, `data.email`,
  `refresh_token`, `access_token`, `new_refresh`, `jti`, `new_jti`, or
  `family_id`'s raw value into any log call (positional or `extra`). A test in §5
  asserts the captured log text contains neither the password nor the raw token.

### 3.2 — `#A2` `register_user` has no logging (minor · spec 06)

- **File:** `backend/src/inkstave/services/user.py` (line ~43)
- **Problem:** `register_user` emits no logs. Both the pre-check
  (`email_exists` → `EmailAlreadyExistsError`, ~line 48–49) and the
  unique-violation **race** (`IntegrityError` → `EmailAlreadyExistsError`,
  ~lines 61–62) silently convert a duplicate-email conflict into an error with no
  trace, and a successful signup leaves no audit line.
- **Fix:** Add a module logger and emit:
  - **INFO** on **successful registration** (after `session.refresh(user)`,
    before `return user`): `logger.info("user registered", extra={"user_id": user.id})`.
    Log `user_id`, **not** the email or password.
  - **WARNING** on the **duplicate-email conflict** — at both raise sites
    (the pre-check and the `IntegrityError` race). Log the event only; do **not**
    log the email. Example: `logger.warning("registration rejected: email already exists")`.

### 3.3 — `#A3` WS auth `except Exception` swallows the error with no log (minor · spec 29)

- **File:** `backend/src/inkstave/collab/ws/router.py` (line ~84, inside `collab_ws`)
- **Problem:** The WebSocket auth block catches **`except Exception`** around
  `authenticate_ws_token(...)` and closes with `CLOSE_UNAUTHORIZED` while logging
  **nothing**. A bug in token decoding, a DB error, or a genuine auth rejection
  all look identical and silent — there is no signal that auth failed or why.
- **Fix:**
  1. **Narrow the catch** to the specific authentication error the dependency
     raises. `authenticate_ws_token` → `_resolve_user` raises
     **`NotAuthenticatedError`** (defined in `inkstave.auth.dependencies`,
     subclass of `UnauthorizedError`). Import it and change
     `except Exception:` → `except NotAuthenticatedError:`.
  2. **Log a WARNING** before closing, with non-sensitive context — the
     `project_id` and `document_id` (both already in scope as path params) — and
     **never** the `token`. Add a module logger
     (`logger = logging.getLogger(__name__)`). Example:
     `logger.warning("collab ws auth failed", extra={"project_id": str(project_id), "document_id": str(document_id)})`.
  3. **Do not change the close behaviour:** the socket must still
     `await websocket.close(code=CLOSE_UNAUTHORIZED)` and `return` exactly as
     today. Only the catch type and the added log line change.
  > Note: narrowing the catch means a non-auth error (e.g. a DB failure) now
  > propagates instead of being silently masked as "unauthorized". That is the
  > intended, correct behaviour — such errors should surface, not hide. Do not
  > re-broaden the catch to suppress them.

### 3.4 — `#A4` Rate-limit body-parse failure silently sets `email = ""` (nit · spec 08/52)

- **File:** `backend/src/inkstave/auth/rate_limit.py` (line ~73, in `_identity`)
- **Problem:** When the request body cannot be parsed as JSON, the `except
  Exception:` block sets `email = ""` with no log, so the limiter silently falls
  back to IP-only identity for an email-scoped route. The fallback is invisible,
  making a misbehaving client or a body-parsing regression hard to diagnose.
- **Fix:** Add a **DEBUG** (or WARNING) log inside the `except` block before the
  `email = ""` fallback, so the degraded identity is visible. This module already
  has `logger = logging.getLogger("inkstave.ratelimit")` — reuse it. Log the
  `scope` only; do **not** log the body or any email. Example:
  `logger.debug("rate-limit identity: body parse failed, using ip only (scope=%s)", scope)`.
  **Behaviour is unchanged** — the fallback still happens; this is observability
  only.

## 4. Overleaf reference (study only — never copy)

> There is **no Overleaf equivalent** for this work. Inkstave's auth subsystem
> (argon2id hashing, JWT access/refresh with rotation + reuse detection, the
> Redis-backed refresh store, and the JWT-authenticated collab WebSocket) is an
> independent from-scratch implementation; Overleaf's session/auth model differs
> and is AGPLv3. **Do not read or copy any Overleaf code for this fix-pack.**
> Follow only the existing in-repo logging conventions cited in §2.

## 5. Acceptance criteria

Each is independently verifiable.

1. **`#A1`** A failed login (`login` with bad credentials) produces a **WARNING**
   log record from `services.auth`.
2. **`#A1`** A refresh-token **reuse** attempt (replaying an already-rotated
   token, the `record.rotated` branch) produces a **WARNING** log record signalling
   reuse / family revocation.
3. **`#A1`** A **successful login** produces an **INFO** log record; a successful
   **refresh rotation** produces an **INFO** record; a **logout** with a valid
   token produces an **INFO** record.
4. **`#A1` / overriding constraint** Across all auth flows above, **no** captured
   log record contains the password string or any raw access/refresh token value
   (asserted directly in a test).
5. **`#A2`** A successful registration produces an **INFO** record (with
   `user_id`, not the email); a duplicate-email conflict (pre-check **and** the
   `IntegrityError` race) produces a **WARNING** record. No record contains the
   password.
6. **`#A3`** The WS auth catch is narrowed to `NotAuthenticatedError`; an invalid
   token logs a **WARNING** carrying `project_id`/`document_id` and **still** closes
   with `CLOSE_UNAUTHORIZED`. The token string is not in the log.
7. **`#A4`** When the rate-limit body cannot be parsed, a log record (DEBUG or
   WARNING) is emitted noting the IP-only fallback; the resulting identity and
   limiter behaviour are unchanged.
8. The full backend test suite is green and runs in **< 2 minutes**.

## 6. Test plan

> Keep the combined suite under 2 minutes. No real network/LLM/Redis where it can
> be mocked; use fakes/stubs and `caplog`. Add new tests under
> `backend/tests/unit/` (e.g. `test_auth_logging_92.py`).

- **Stay green:** All existing auth, user-service, rate-limit, and collab-WS tests
  must continue to pass — behaviour (status codes, close codes, error messages) is
  unchanged.
- **New / updated tests proving each fix** (use `caplog.at_level(logging.INFO)` /
  `caplog.set_level(...)` and assert on `record.levelname` and `record.message` /
  `getMessage()`):
  - **`#A1` failed login:** call `login(...)` with wrong credentials, expect
    `InvalidCredentialsError`, and assert a WARNING record was emitted by the
    `services.auth` logger.
  - **`#A1` refresh reuse:** drive `refresh_tokens(...)` against a fake/in-memory
    `RefreshStore` whose `get_refresh` returns a record with `rotated=True`, expect
    `RefreshError(_REUSE_DETECTED)`, and assert a WARNING reuse record.
  - **`#A1` success paths:** assert INFO records on successful `login`,
    `refresh_tokens` rotation, and `logout` (valid token), using fakes for the
    token service + refresh store so no real Redis/JWT crypto is needed beyond what
    the existing unit tests already stub.
  - **`#A1` secret-redaction assertion (the key test):** capture the full log text
    across the success + failure flows and assert it contains **neither** the test
    password **nor** the raw access/refresh token string (e.g.
    `assert PASSWORD not in caplog.text and raw_token not in caplog.text`).
  - **`#A2`:** assert INFO on `register_user` success and WARNING on the
    duplicate-email pre-check **and** the `IntegrityError` race (force the race by
    making `email_exists` return `False` then `session.flush` raise
    `IntegrityError`). Assert the password is not in `caplog.text`.
  - **`#A3`:** a unit/integration test of the collab WS auth path with an invalid
    token asserts (a) a WARNING is logged with `project_id`/`document_id` context,
    (b) the socket is closed with `CLOSE_UNAUTHORIZED`, and (c) the catch no longer
    swallows a non-`NotAuthenticatedError` (a different exception type propagates).
    Reuse the existing collab-WS test harness/fakes; do not stand up real Redis.
  - **`#A4`:** call `_identity(...)` (or exercise the dependency) with a request
    whose `.json()` raises, and assert a DEBUG/WARNING record is emitted and the
    returned identity is the IP-only fallback.
- **Performance/budget note:** All new tests are in-memory/mocked (fake token
  service, fake refresh store, `caplog`); no real network, LLM, Redis, or sleeps.
  The 2-minute suite budget is unaffected.

## 7. Definition of Done

- [ ] All 4 issues in §3 fixed (auth-flow logging, registration logging, narrowed
      WS catch + warning, rate-limit fallback log).
- [ ] All acceptance criteria in §5 pass — including criterion 4: **no log record
      contains a password or raw token**.
- [ ] New/updated `caplog` tests in §6 written and green.
- [ ] Full suite runs in **< 2 minutes**.
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] Edits limited to the files in §2 — no out-of-scope files touched; no
      control-flow / status-code / close-code / error-message changes.
- [ ] Logging matches the existing style (module `getLogger`, %-args / `extra=`).
- [ ] No Overleaf code copied; stack unchanged.
