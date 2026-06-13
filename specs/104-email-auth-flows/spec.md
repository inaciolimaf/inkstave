# Spec 104 — Email link-based account flows (verify / magic-link / reset) (requirements)

## 1. Summary

This spec delivers the three end-to-end **email link** account flows that the
foundation specs left half-wired: (1) **email verification** — on registration
the user receives a link that, when clicked, sets `email_confirmed`; (2)
**passwordless login (magic link)** — a user requests a one-time login link and
clicking it issues the normal JWT access+refresh pair; (3) **password reset** — a
user requests a reset link, clicks it, sets a new password, and every existing
session is revoked. All three share one secure, hashed-at-rest, single-use,
expiring token store (`auth_tokens`). Spec 103 already built the email *delivery*
pipeline and two of the templates; this spec replaces 103's throwaway token URLs
with persisted tokens, adds the callback endpoints, the abuse protection, and the
frontend pages, and adds the one missing template (`magic_login`).

## 2. Context & dependencies

- **Depends on:**
  - **Spec 06** — `User` model (`db/models/user.py`) with the existing
    `email_confirmed` column; password rules (`auth/password.py`,
    `frontend/src/lib/validation.ts` → `makePasswordSchema`: 8–72 chars, letter +
    digit) reused by the reset form.
  - **Spec 07/08** — `TokenService` (`auth/tokens.py`) for issuing the
    access+refresh pair, `RefreshStore` (`auth/refresh_store.py`) including
    `revoke_user(user_id)` (the "sign out all sessions" cutoff used by reset), and
    the thin auth routes (`api/routes/auth.py`).
  - **Spec 09** — frontend auth foundation: `frontend/src/auth/auth-context.tsx`,
    `frontend/src/lib/api-client.ts`, `frontend/src/lib/token-store.ts`,
    `frontend/src/pages/login.tsx` / `register.tsx`, the react-router tree in
    `frontend/src/App.tsx`, and the token-callback page precedent
    `frontend/src/features/settings/ConfirmEmailPage.tsx`.
  - **Spec 39 + 103** — the async mailer: `EmailEnqueuer`
    (`mailer/enqueuer.py`), `send_email_job` (`mailer/jobs.py`), `render_email` +
    `_TEMPLATES` (`mailer/templates.py`, which already defines
    `email_verification` and `password_reset`), and the
    `password_reset_token_ttl` / `email_verification_token_ttl` /
    `app_base_url` / `frontend_url` settings (`config_groups.py`). 103 also added
    the placeholder `POST /api/auth/forgot-password` route in `api/routes/auth.py`
    and the fire-and-forget verification enqueue in `register`.
  - **Spec 52** — rate limiting: the `rate_limit(scope)` dependency factory
    (`auth/rate_limit.py`, with email-aware identity for `login`/`register` and
    the `forgot_password` → `rate_limit_auth_password` mapping) and the
    `security/rate_limit.py` helpers (`check_rate_limit`, `policy_from_setting`).
  - **Spec 59** — the hashed single-use token pattern in `services/account.py`
    (`start_email_change` / `confirm_email_change`) and the helpers
    `generate_token()` / `hash_token()` in `services/sharing_common.py`. This
    spec generalises that pattern into a dedicated table.
  - **Spec 94** — the injectable `Clock` (`inkstave/time.py`, `SYSTEM_CLOCK`)
    used everywhere expiry is computed/checked, for deterministic tests.
  - **Spec 51** — structured logging (`observability/log.py`) for security events;
    secrets are auto-redacted, so raw tokens must never be logged.
- **Unlocks:** trustworthy email ownership (gate features on `email_confirmed`),
  a passwordless sign-in path, and self-service password recovery.
- **Affected areas:** backend (`db/models/`, `migrations/`, `services/`,
  `api/routes/auth.py`, `schemas/`, `auth/rate_limit.py`, `config_groups.py`),
  frontend (`src/features/auth/`, `src/App.tsx`, `src/lib/`), config
  (`.env.example`), docs (`docs/adr/`).

## 3. Goals

- One `auth_tokens` table storing tokens **by purpose**, hashed at rest, with
  user/email binding, expiry, single-use consumption, and per-purpose TTLs.
- Email-verification flow: request (auto on register + a resend endpoint) →
  callback that sets `email_confirmed`.
- Magic-link passwordless login: request → callback that issues the real JWT pair
  via the existing `TokenService`/`RefreshStore`.
- Password-reset flow: request (own 103's `forgot-password` trigger) → callback
  that sets a new password, **revokes all sessions**, and confirms the email.
- All request endpoints are **non-enumerating** and **rate-limited** (per email +
  per IP) reusing spec 52; each request enqueues **exactly one** send job.
- Frontend pages for every request + callback, with loading/error/success states,
  reusing the password schema from spec 06.
- Tests cover token lifecycle, all three round trips, non-enumeration, session
  revocation on reset, and the enqueue-exactly-one guarantee — with no real email
  and the full suite under 2 minutes.

## 4. Non-goals (explicitly out of scope)

- **No typed OTP / numeric codes** — every flow is a single clicked link.
- No email *delivery* changes — transport, Mailpit, Resend, and the
  `send_email_job` are spec 103/39 and stay untouched.
- No social/OAuth login, WebAuthn, or 2FA (later/never specs).
- No "remember device" / trusted-device logic for magic links.
- No changes to the credential login (`POST /auth/login`) beyond optionally
  gating it on `email_confirmed` via a config flag (§5.5).
- No admin UI to inspect/revoke outstanding tokens.
- No rate-limit infrastructure changes — reuse spec 52 as-is.

## 5. Detailed requirements

### 5.1 Data model

A new table `auth_tokens` holds every link token for the three flows. Only the
**hash** of the token is stored; the raw token exists only inside the emailed URL.

#### `auth_tokens`

| Column | Type | Constraints / notes |
| --- | --- | --- |
| `id` | UUID PK | via `UUIDPrimaryKeyMixin` (server default `gen_random_uuid()` per existing convention). |
| `purpose` | `String(32)` (or a PG enum) | one of `email_verify`, `magic_login`, `password_reset`. **NOT NULL**. Stored as a plain `String` with a `CHECK (purpose IN (...))` constraint named `ck_auth_tokens_purpose` (simpler than a PG enum migration; matches the project's lightweight style). |
| `user_id` | UUID FK → `users.id` | **NOT NULL**, `ondelete="CASCADE"` (tokens die with the account). |
| `email` | `CITEXT` | **NOT NULL**. The address the link was issued for — bound at creation so a later email change cannot be confirmed by an old link. For `email_verify` this is the address being confirmed; for `magic_login`/`password_reset` it is the user's current email at issue time. |
| `token_hash` | `Text` | **NOT NULL, UNIQUE** (`uq_auth_tokens_token_hash`). `sha256(raw)` hex, exactly as `services/sharing_common.hash_token`. Never the raw token. |
| `expires_at` | `DateTime(timezone=True)` | **NOT NULL**. `created_at + per-purpose TTL`. |
| `consumed_at` | `DateTime(timezone=True)` | nullable; set on first successful use (single-use). A non-null value means the token is spent. |
| `created_at` | `DateTime(timezone=True)` | via `TimestampMixin` (also gives `updated_at`). |

**Indexes / constraints:**

- Unique index on `token_hash` (the only lookup key; raw token never queried).
- Composite index `ix_auth_tokens_user_purpose` on `(user_id, purpose)` to make
  "invalidate older tokens of this purpose for this user" cheap.
- A partial index `ix_auth_tokens_active` on `(purpose, expires_at)`
  `WHERE consumed_at IS NULL` to support a future expiry sweep (sweep itself is
  out of scope; the index is cheap and forward-looking — mirror the partial-index
  style already used on `users`).
- The `purpose` CHECK constraint above.

**Alembic migration:** add one migration
`backend/migrations/versions/<ts>_create_auth_tokens.py` with
`down_revision = "e2f4a8b13c90"` (the current head — verify before writing; never
edit a released migration). Use `postgresql.CITEXT` for `email` (CITEXT is
already enabled in the DB by the users migration). Provide a working `downgrade`
that drops the table.

> **Reuse vs. new table (decision):** spec 59 stored the email-change token on the
> `users` row (one in-flight token per user). That does not generalise to three
> concurrent purposes, multiple outstanding magic links, or an email binding
> distinct from the account's current email. A dedicated table is the right
> reuse-and-extend of the spec-59 *pattern* (hash-at-rest + single-use + expiry),
> not a duplication. Record this in the ADR. The spec-59 email-change token stays
> on `users` (do not migrate it).

### 5.2 Backend / API

#### 5.2.1 Token service — `services/auth_tokens.py` (new)

A small async service owning the table; it is the only code that creates/consumes
tokens. Uses `generate_token()` / `hash_token()` from `services/sharing_common.py`
and an injected `Clock` (default `SYSTEM_CLOCK`) for all time math.

```python
PURPOSES = ("email_verify", "magic_login", "password_reset")

@dataclass(frozen=True)
class IssuedToken:
    raw: str          # goes only into the emailed URL
    token: AuthToken  # the persisted row (hash only)

async def issue_token(
    session: AsyncSession,
    *,
    user_id: UUID,
    email: str,
    purpose: str,
    ttl_seconds: int,
    clock: Clock = SYSTEM_CLOCK,
) -> IssuedToken: ...

async def consume_token(
    session: AsyncSession,
    *,
    raw_token: str,
    purpose: str,
    clock: Clock = SYSTEM_CLOCK,
) -> AuthToken: ...
```

**`issue_token` contract:**

1. **Invalidate older active tokens of the same `(user_id, purpose)`** before
   inserting: set `consumed_at = clock.now()` on every row for that pair where
   `consumed_at IS NULL`. (A new request supersedes any outstanding link — the
   most recent link is the only valid one.)
2. Generate `raw = generate_token()` (32 random bytes, url-safe), compute
   `token_hash = hash_token(raw)`, insert a row with the bound `email`,
   `expires_at = clock.now() + ttl_seconds`.
3. Return `IssuedToken(raw=raw, token=row)`. **Never log `raw`.** Emit a spec-51
   security event `auth_token_issued` with `{user_id, purpose}` only (no raw, no
   hash).

**`consume_token` contract (constant-time, single-use):**

1. Look the row up **only by `token_hash = hash_token(raw_token)`** (constant-time
   in effect: an unknown token hashes to a value that simply misses; we never
   branch on a partial match or compare raw strings). Filter by `purpose` too, so
   a verify token can never be redeemed at the reset callback.
2. If no row, or `purpose` mismatches → raise `BadRequestError("Invalid or
   already-used link.")` (uniform message; see §5.2.6 error semantics).
3. If `consumed_at IS NOT NULL` → raise the **same** `BadRequestError` (used links
   and unknown links are indistinguishable to the caller).
4. If `expires_at < clock.now()` → raise `GoneError("This link has expired.")`
   (HTTP 410). (Distinct from invalid: an expired-but-real link tells the user to
   request a fresh one; this does not leak existence because the link itself was
   only ever sent to the address owner.)
5. Otherwise set `consumed_at = clock.now()`, flush, and return the row. The
   single-use guarantee is enforced **inside the same transaction** as the action
   it authorizes (verify / login / reset) so a crash mid-action does not burn the
   token without effect, and a replay after success is rejected.
   - Concurrency: rely on the unique `token_hash` and the row update; a
     `SELECT ... FOR UPDATE` on the row before setting `consumed_at` prevents a
     double-spend race on two simultaneous clicks. Document this lock.

#### 5.2.2 Flow services — extend `services/account.py` (or a new `services/email_auth.py`)

Prefer a new module `services/email_auth.py` to keep `account.py` focused; it may
import the helpers there. It exposes the three flows' business logic; the routes
stay thin (matching the existing `api/routes/auth.py` style).

- `async def request_email_verification(session, user, *, settings, clock) -> str`
  → issues an `email_verify` token bound to `user.email`, TTL
  `settings.email_verification_token_ttl`, returns the raw token (route builds the
  URL + enqueues).
- `async def confirm_email_verification(session, *, raw_token, clock) -> User`
  → `consume_token(purpose="email_verify")`; load the user; **only confirm if the
  bound `email` still equals the user's current email** (else raise
  `BadRequestError` — the address changed since the link was sent); set
  `user.email_confirmed = True`; idempotent if already confirmed (still 200).
- `async def request_magic_login(session, *, email, settings, clock) -> str | None`
  → look up the user by normalised email; if none, return `None` (route still
  responds identically — non-enumerating); else issue a `magic_login` token (TTL
  `settings.magic_login_token_ttl`) and return the raw token.
- `async def complete_magic_login(session, token_service, refresh_store, *, raw_token, clock) -> TokenPair`
  → `consume_token(purpose="magic_login")`; load user; if the bound `email` no
  longer matches the user's email raise `BadRequestError`; **reuse the exact
  issuance from `services/auth.login`** (new `family_id`, `create_access_token`,
  `create_refresh_token`, `refresh_store.store_refresh`) and return a `TokenPair`.
  Factor the shared issuance into a helper `issue_token_pair(token_service,
  refresh_store, user)` and call it from both `auth.login` and here (do not
  duplicate the four lines). Optionally also set `email_confirmed = True` on a
  successful magic login (clicking a link proves ownership) — do this and note it
  in the ADR.
- `async def request_password_reset(session, *, email, settings, clock) -> str | None`
  → same non-enumerating lookup; issue a `password_reset` token (TTL
  `settings.password_reset_token_ttl`); return raw or `None`.
- `async def complete_password_reset(session, refresh_store, hasher, *, raw_token, new_password, clock) -> None`
  → `consume_token(purpose="password_reset")`; load user; validate the new
  password (reuse the spec-06 rule: 8–72, letter+digit, and reject if it contains
  the email local-part, exactly as `account.change_password` does); set
  `user.hashed_password = await asyncio.to_thread(hasher.hash, new_password)`;
  **set `email_confirmed = True` if not already** (the reset link proves
  ownership of the inbox); then **`await refresh_store.revoke_user(user.id)`** to
  sign out every session (reuse spec 07/08 revocation). Emit a spec-51
  `password_reset_completed` security event `{user_id}`.

#### 5.2.3 Endpoints (all under the existing `/auth` router, served at `/api/v1/auth/...`)

All request bodies are Pydantic v2 schemas in `schemas/auth.py`. Responses reuse
the existing `MessageResponse` and `TokenPair`. Errors use the standard
`ErrorEnvelope`.

| # | Method & path | Auth | Request | Success | Rate limit scope | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `POST /auth/verify-email/resend` | optional / public | `{ "email": EmailStr }` | `202` `MessageResponse` | `verify_email` (per email+IP) | Non-enumerating: always 202; enqueue only if a user exists **and is not yet confirmed**. |
| 2 | `POST /auth/verify-email/confirm` | none (token authorizes) | `{ "token": str }` | `200` `UserPublic` | `verify_email` (light) | Sets `email_confirmed`. Idempotent. 400 invalid/used, 410 expired. |
| 3 | `POST /auth/magic-link` | none | `{ "email": EmailStr }` | `202` `MessageResponse` | `magic_link` (per email+IP) | Non-enumerating; enqueue `magic_login` email only if user exists. |
| 4 | `POST /auth/magic-link/callback` | none | `{ "token": str }` | `200` `TokenPair` | `magic_link_callback` | Issues real JWT pair (logs the user in). 400 invalid/used, 410 expired. |
| 5 | `POST /auth/forgot-password` | none | `{ "email": EmailStr }` | `202` `MessageResponse` | `forgot_password` (already mapped, spec 52/103) | **Owned here now:** replace 103's throwaway-token enqueue with a real `password_reset` token. Non-enumerating. |
| 6 | `POST /auth/reset-password` | none (token authorizes) | `{ "token": str, "new_password": str }` | `200` `MessageResponse` | `reset_password` | Sets password, revokes all sessions, confirms email. 400 invalid/used/weak-password, 410 expired. |

Endpoint details:

- **Registration (existing `register` route):** keep its fire-and-forget
  verification enqueue, but **replace the throwaway `generate_token()` URL** with
  a real `email_verify` token issued via `request_email_verification`. Build
  `verify_url = f"{settings.frontend_url}/verify-email?token={raw}"` and enqueue
  the existing `email_verification` template (unchanged). Registration must still
  succeed and return `201` even if enqueueing is a no-op in tests.
- **#1 resend:** if the user exists and `email_confirmed is False`, issue a token
  and enqueue `email_verification`. If the user is already confirmed or does not
  exist, **do not enqueue** but still return the identical `202`. (Confirmed users
  silently get nothing — avoids spamming and avoids enumeration.)
- **#2 confirm / #4 callback / #6 reset:** these are `POST` (not `GET`) so the
  raw token is in the JSON body, not the URL/Referer/server logs. The frontend
  callback page reads `?token=` from the URL and POSTs it (the same pattern as
  `ConfirmEmailPage`). Each is unauthenticated — the token alone authorizes.
- **#5 forgot-password:** the route signature already exists (103). Change its
  body to call `request_password_reset`, build
  `reset_url = f"{settings.frontend_url}/reset-password?token={raw}"`, and enqueue
  the existing `password_reset` template only when a user was found. Return the
  same `202` `MessageResponse` in both branches.
- **#3 magic-link:** build
  `magic_url = f"{settings.frontend_url}/magic-link?token={raw}"` and enqueue the
  **new** `magic_login` template (§5.4).

#### 5.2.4 Schemas (`schemas/auth.py`)

Add (EmailStr request bodies; reuse `MessageResponse`/`TokenPair`/`UserPublic`):

```python
class EmailOnlyRequest(BaseModel):       # magic-link, resend; forgot-password may reuse ForgotPasswordRequest
    email: EmailStr

class TokenOnlyRequest(BaseModel):        # verify-confirm, magic-callback
    token: str = Field(min_length=1, max_length=512)

class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=8, max_length=72)
```

Mirror the existing `ForgotPasswordRequest` for the email-only shape where one
already exists; do not introduce a second incompatible email schema. The
`new_password` field constraints mirror spec 06; the service re-validates
letter+digit + email-local-part rules (schema length checks are not sufficient).

#### 5.2.5 Rate limiting (reuse spec 52)

Extend `auth/rate_limit.py`'s `_SCOPE_SETTING` and `_EMAIL_SCOPES`:

- Add scopes `verify_email`, `magic_link`, `reset_password` mapped to new settings
  (§5.5). Add `verify_email`, `magic_link` to `_EMAIL_SCOPES` so identity is
  `ip:email` (throttles per address **and** per IP, the requested "per email + per
  IP" cap). `forgot_password` is already mapped (→ `rate_limit_auth_password`).
- The callback endpoints (#2/#4/#6) get a **looser** IP-only limit (e.g.
  `reset_password`, `magic_link_callback`, `verify_email_confirm`) to blunt token
  brute force without locking out a legitimate user retrying a click. A
  url-safe 32-byte token is unguessable, so these caps are defence-in-depth.
- Attach via `dependencies=[Depends(rate_limit("<scope>"))]` exactly like the
  existing auth routes. The limiter fails open on Redis outage (existing
  behaviour) — keep that.
- **Token issuance cap:** the §5.2.1 "invalidate older tokens of the same
  purpose" rule already bounds outstanding tokens per user to one. The per-email
  request rate limit bounds issuance rate. No separate counter needed.

#### 5.2.6 Error & non-enumeration semantics (uniform)

- **Request endpoints (#1, #3, #5):** always `202` with a generic
  `MessageResponse` (e.g. "If that email is registered, a link is on its way.")
  regardless of whether the user exists / is confirmed. Enqueue conditionally. No
  field in the response or its timing reveals existence. (The DB lookup is the
  same constant work either way; do not add an artificial delay.)
- **Callback endpoints (#2, #4, #6):** `400 BadRequestError` for unknown / used /
  wrong-purpose tokens (one message: *"Invalid or already-used link."*); `410
  GoneError` for an expired but otherwise valid token; `400` for a weak new
  password on reset (field error). Never reveal whether a token *ever* existed.
- **Security logging (spec 51):** log `auth_token_issued`,
  `auth_token_consumed` (with `purpose`, `user_id`, and `outcome`), `magic_login_succeeded`,
  `password_reset_completed`, and `auth_token_invalid` (no user_id when unknown).
  **Never log the raw token or its hash** (the spec-51 redactor covers
  `*token*`-ish keys, but do not pass the raw value at all).

### 5.3 Frontend / UI (Vite + React + shadcn)

New feature folder `frontend/src/features/auth/` (mirroring
`features/settings/`), plus routes in `frontend/src/App.tsx`. A thin API module
`frontend/src/features/auth/api.ts` wraps `apiClient` (auth: false, since these
are pre-login), returning typed results — same style as
`features/settings/api.ts`.

Routes (all public / reachable signed-out, like `/settings/confirm-email`):

| Route | Component | Behaviour |
| --- | --- | --- |
| `/verify-email` | `VerifyEmailPage` | Reads `?token`; POSTs to `verify-email/confirm` exactly once (guard with a `ran` ref, copy `ConfirmEmailPage`). States: loading → success ("Email verified" + link to /login or /projects) / expired (offer "resend") / invalid. |
| `/verify-email/resend` (or a panel on the login page) | `ResendVerificationForm` | Email input → POST `verify-email/resend`; always shows the same "check your inbox" success regardless of response. |
| `/magic-link` *(request)* | `MagicLinkRequestPage` | Email input → POST `magic-link`; success state "Check your inbox for a sign-in link." (non-enumerating copy). Link from the login page ("Email me a sign-in link"). |
| `/magic-link` *(callback — same path, token present)* | within `MagicLinkRequestPage` or a sibling `MagicLinkCallbackPage` | If `?token` present: POST `magic-link/callback`; on success store the returned pair via `tokenStore.setTokens` + `auth-context` (reuse the same store/`bootstrap` path as `login`) and `navigate("/projects")`. States: loading → redirect / expired / invalid (offer "request a new link"). |
| `/forgot-password` | `ForgotPasswordPage` | Email input → POST `forgot-password`; success "If that email is registered, a reset link is on its way." Linked from the login page. |
| `/reset-password` | `ResetPasswordPage` | Reads `?token`; password + confirm fields validated with the **shared** `makePasswordSchema` (spec 06, `lib/validation.ts`); POST `reset-password`; on success show "Password updated — please sign in" and redirect to `/login` (tokens were all revoked, so do **not** auto-login). States: loading (initial token presence check) → form → submitting → success / expired / invalid. |

Frontend details:

- **Login-page wiring:** add "Forgot password?" and "Email me a sign-in link"
  links to `frontend/src/pages/login.tsx`; optionally surface a "Didn't get a
  verification email? Resend" affordance. Do not restructure the login form.
- **Auth context:** add a `loginWithTokenPair(pair: TokenPair)` helper to
  `auth-context.tsx` that stores the pair and fetches `/users/me`, reused by the
  magic-link callback (so it shares the exact post-login path as `login`). Keep
  changes minimal and typed.
- **States:** every page renders explicit loading / success / error (expired vs.
  invalid) using shadcn `Card`/`Alert`/`Button`/`Input`/`Form` (already in
  `components/ui/`). Buttons show a `Loader2` spinner while pending (match
  `register.tsx`). Disable the submit while in flight.
- **i18n:** add an `auth` namespace key block for the new copy (the project uses
  `react-i18next`; `ConfirmEmailPage` already reads from the `auth` namespace).
- **Accessibility:** inputs have associated `FormLabel`s; error `Alert`s use
  `role="alert"`; the callback pages announce status changes.
- **`PublicOnly` vs public:** these pages must be reachable while signed-out and
  should not be wrapped in `RequireAuth`. The reset/verify/magic callbacks are
  reachable even when signed in (a user may click a link in another tab); do
  **not** wrap them in `PublicOnly` (which would bounce a signed-in user away from
  a valid action). The request pages (`forgot-password`, `magic-link` request)
  may use `PublicOnly` like `/login`.

### 5.4 Real-time / jobs / external integrations

- **No new ARQ job.** Every email goes through the existing
  `EmailEnqueuer.enqueue_email(template=..., to=..., context=...)` →
  `send_email_job` (spec 39/103). Handlers never call `sender.send` inline.
- **Templates:** reuse 103's `email_verification` (context `{user_name?,
  verify_url}`) and `password_reset` (context `{user_name?, reset_url}`)
  **unchanged**. **Add one** renderer to `mailer/templates.py` and register it in
  `_TEMPLATES`:
  - `magic_login` — context `{user_name?, magic_url}`. Subject e.g. *"Your
    Inkstave sign-in link"*. Text + HTML in the existing style (greeting, one-line
    reason, the `magic_url` link built from `frontend_url` at the call site, an
    "if you didn't request this, ignore" footer). HTML MUST `escape(...)` every
    interpolated value, including `escape(str(magic_url), quote=True)` inside the
    `href`, exactly like the other renderers (spec-40 XSS rule). Add it to the
    inventory in the ADR.
- **URL construction at the call site:** every link is built in the route/service
  as `f"{settings.frontend_url}/<path>?token={raw}"` (matching `change_email`'s
  precedent). Templates receive a ready-made absolute URL and know nothing about
  settings. (`frontend_url` is the SPA base, e.g. `http://localhost:5173`;
  `app_base_url` remains the spec-103/39 default for any non-SPA link — keep using
  `frontend_url` for these three flows for consistency with the existing
  email-change and invite links.)

### 5.5 Configuration

#### New / changed settings (`config_groups.py`)

| Setting | Default | Purpose |
| --- | --- | --- |
| `password_reset_token_ttl: int` | `3600` | **Already added by spec 103** — reuse, do not re-add. Password-reset link lifetime (s). |
| `email_verification_token_ttl: int` | `86400` | **Already added by spec 103** — reuse. Verification link lifetime (s). |
| `magic_login_token_ttl: int` | `600` | **New.** Magic-link lifetime (s) — short (10 min) because it grants a session. |
| `require_verified_email_to_login: bool` | `false` | **New toggle.** When `true`, `POST /auth/login` rejects an unconfirmed user with `403`/`UnauthorizedError` ("Please verify your email first.") and the magic-link / reset flows still work (they confirm the email). Default `false` to keep existing behaviour and not break current tests. |
| `rate_limit_verify_email: str` | `"5/3600"` | **New.** Per email+IP cap on resend/verify requests. |
| `rate_limit_magic_link: str` | `"5/3600"` | **New.** Per email+IP cap on magic-link requests. |
| `rate_limit_reset_password: str` | `"10/3600"` | **New.** IP cap on the reset-password callback (brute-force blunting). |

`forgot-password` continues to reuse `rate_limit_auth_password` (5/3600), already
mapped in `auth/rate_limit.py`.

#### `.env.example`

Add to the email/auth block (the spec-103 block already documents the two TTLs):

```dotenv
# Email link-based auth flows (spec 104).
MAGIC_LOGIN_TOKEN_TTL=600                  # passwordless sign-in link lifetime (seconds)
REQUIRE_VERIFIED_EMAIL_TO_LOGIN=false      # if true, credential login requires a confirmed email
RATE_LIMIT_VERIFY_EMAIL=5/3600             # per email+IP cap on verification (re)send
RATE_LIMIT_MAGIC_LINK=5/3600              # per email+IP cap on magic-link requests
RATE_LIMIT_RESET_PASSWORD=10/3600          # per-IP cap on reset-password callbacks
```

(`PASSWORD_RESET_TOKEN_TTL` / `EMAIL_VERIFICATION_TOKEN_TTL` are already present
from spec 103 — do not duplicate them.)

#### Feature flag default

`require_verified_email_to_login = false` by default so this spec adds capability
without changing the login contract; flipping it on is an operator decision
documented in the ADR.

## 6. Overleaf reference (study only — never copy)

Verified present in `../overleaf/`:

- `services/web/app/src/Features/PasswordReset/PasswordResetHandler.mjs` — how
  Overleaf generates, stores (hashed, TTL'd, single-use), and validates a
  password-reset token, and how it invalidates the token after use. Learn the
  **token lifecycle**; Inkstave implements its own `auth_tokens` table + service.
- `services/web/app/src/Features/PasswordReset/PasswordResetController.mjs` — the
  request/callback split and the **non-enumerating** request response. Learn the
  **HTTP shape**; write Inkstave's own routes.
- `services/web/app/src/Features/PasswordReset/PasswordResetRouter.mjs` — route
  wiring only.
- `services/web/app/src/Features/Authentication/AuthenticationController.mjs` and
  `SessionManager.mjs` — how a successful auth establishes a session/token. Learn
  the **issuance seam**; Inkstave already has `TokenService` + `RefreshStore`
  (spec 07/08) and reuses `auth.login`'s issuance — do not mirror Overleaf's
  session model.

**No Overleaf equivalents (state explicitly):**

- **Passwordless / magic-link login has no Overleaf Community equivalent** —
  Overleaf CE authenticates by password (or institutional SSO, out of scope). The
  magic-link flow is Inkstave-specific and written from scratch.
- The single shared `auth_tokens` table covering three purposes is Inkstave's
  design; Overleaf scatters per-feature token handling. No structure to copy.

## 7. Acceptance criteria

1. **Given** the migration is applied, **when** the schema is inspected, **then**
   `auth_tokens` exists with `purpose` (CHECK-constrained to the three values),
   `user_id` FK (CASCADE), `email` (CITEXT), unique `token_hash`, `expires_at`,
   nullable `consumed_at`, timestamps, and the documented indexes.
2. **Given** `issue_token(purpose="X")` is called twice for the same user, **when**
   the second call runs, **then** the first token's `consumed_at` is set (older
   tokens of the same purpose are invalidated) and only the raw token from the
   second call verifies; the raw token is returned **once** and never persisted.
3. **Given** a freshly issued token, **when** `consume_token` is called with the
   correct raw token and matching purpose before expiry, **then** it returns the
   row and sets `consumed_at`; **when** called a second time with the same token,
   **then** it raises `BadRequestError` (single-use); **when** the purpose passed
   differs from the token's purpose, **then** it raises `BadRequestError`.
4. **Given** a token whose `expires_at` is in the past (driven by an **injected
   clock**), **when** `consume_token` runs, **then** it raises `GoneError` (410)
   and does not consume the token.
5. **Given** registration, **when** a user registers, **then** exactly **one**
   `send_email_job` is enqueued with template `email_verification` to the new
   address, carrying a `verify_url` built from `frontend_url` with a real persisted
   token, and the `201` registration response is unaffected by the email side
   effect (captured fake enqueuer).
6. **Given** the verification callback, **when** `POST /auth/verify-email/confirm`
   is called with a valid token, **then** the user's `email_confirmed` becomes
   `true` and the response is `200`; a second call with the same token returns
   `400`; an expired token returns `410`; an unknown token returns `400`.
7. **Given** `POST /auth/magic-link` for an **unknown** email, **then** the
   response is the same `202` as for a known email and **zero** jobs are enqueued;
   for a **known** user, exactly **one** `magic_login` job is enqueued with a
   `magic_url` from `frontend_url`.
8. **Given** a valid magic-link token, **when** `POST /auth/magic-link/callback`
   is called, **then** the response is `200` with a `TokenPair` whose access token
   authenticates `GET /users/me`, and the issued refresh token is a valid,
   rotatable member in the `RefreshStore` (i.e. issuance reuses spec 07/08). A
   second callback with the same token returns `400`.
9. **Given** `POST /auth/forgot-password` for an **unknown** email, **then** it
   returns the same `202` and enqueues **zero** jobs; for a **known** user,
   exactly **one** `password_reset` job is enqueued with a `reset_url` from
   `frontend_url` and a persisted token (103's throwaway token is gone).
10. **Given** a valid reset token and a logged-in user with an active refresh
    token, **when** `POST /auth/reset-password` succeeds, **then** the password is
    updated (the new password authenticates, the old one does not), `email_confirmed`
    is `true`, **all pre-existing refresh tokens are revoked** (the prior refresh
    token can no longer be rotated — `refresh_store.revoke_user` was called), and
    the response is `200`. A weak `new_password` returns `400` without consuming
    the token's effect being observable beyond the single-use rule.
11. **Given** `require_verified_email_to_login=true`, **when** an unconfirmed user
    calls `POST /auth/login` with correct credentials, **then** they are rejected
    with the verification message; with the flag `false` (default), login
    succeeds as before.
12. **Given** any request endpoint (#1/#3/#5), **when** it is called more than its
    configured per-email+IP limit within the window, **then** it returns `429`
    (spec 52 limiter), and a Redis outage fails open (still allowed).
13. **Given** `render_email("magic_login", {...})`, **then** it returns a subject +
    non-empty text + non-empty HTML, both bodies contain the `magic_url`, and every
    interpolated value is HTML-escaped in the HTML body.
14. **Given** the frontend, **when** a user visits `/reset-password?token=…` and
    submits a valid new password, **then** they see a success state and are
    directed to `/login`; an invalid/expired token shows the corresponding error
    state; the password field is validated with the shared spec-06 schema.
15. **Given** the full automated suite, **when** it runs, **then** it completes in
    **< 2 minutes** and makes **no** real SMTP/Mailpit/Resend connection (sender +
    enqueuer faked) and no raw token appears in any log output.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> No real email; faked sender + capturing enqueuer; injected clock for expiry.

- **Unit (pytest), new `backend/tests/unit/test_auth_tokens_104.py`:**
  - `issue_token` stores only the hash (`token_hash == hash_token(raw)`, raw not
    in any column), sets `expires_at = now + ttl` via an injected clock, and
    invalidates older same-purpose tokens for the user.
  - `consume_token`: happy path consumes + returns; second use raises
    `BadRequestError`; wrong-purpose raises `BadRequestError`; expired (clock
    advanced past `expires_at`) raises `GoneError`; unknown token raises
    `BadRequestError`. Assert (via `caplog`) the raw token never appears.
  - `magic_login` template renders subject+text+html; link in both bodies; HTML
    escaping (mirror the existing `test_*_template` cases in
    `test_email_sender.py`).
- **Integration (pytest + httpx ASGI + test DB + fake Redis/enqueuer),
  `backend/tests/integration/test_email_auth_flows_104.py`:**
  - **Verify:** register → exactly one `email_verification` job captured →
    extract token (from the issued row / the enqueued context's URL via the
    capturing enqueuer) → `verify-email/confirm` sets `email_confirmed`; replay
    → 400; expired (clock) → 410; resend for a confirmed user enqueues **zero**
    jobs but returns 202; resend for an unconfirmed user enqueues exactly one.
  - **Magic link:** request unknown email → 202 + **0** jobs (non-enumeration);
    request known → 202 + **1** `magic_login` job; callback with the token → 200
    `TokenPair`; the access token authenticates `GET /users/me`; replay → 400;
    expired → 410.
  - **Reset:** `forgot-password` unknown → 202 + 0 jobs; known → 202 + 1
    `password_reset` job (assert template + `to` + `reset_url`); obtain a refresh
    token for the user first, then `reset-password` → 200; assert the old refresh
    token can no longer be rotated (`/auth/refresh` → 401) — **proves session
    revocation**; assert the new password logs in and the old does not; weak
    password → 400.
  - **Enqueue-exactly-one** guard for each of the three request flows (capturing
    fake enqueuer count == 1 on the positive branch, 0 on the negative branch).
  - **Flag:** with `require_verified_email_to_login=true`, login of an unconfirmed
    user → rejected; with default → allowed (parametrized).
  - Regression: existing `test_auth.py` and spec-59 `change_email` flow still pass
    (the email-change token on `users` is untouched).
- **Frontend (Vitest + RTL), `frontend/src/features/auth/*.test.tsx`:**
  - `ResetPasswordPage`: renders the form, blocks a weak password (shared schema),
    submits and shows success → directs to `/login`; expired/invalid token token
    states render. Mock `apiClient`.
  - `MagicLinkCallback`: token present → calls callback, stores the pair, navigates
    to `/projects`; error token shows "request a new link".
  - `VerifyEmailPage`: single POST on mount (no double-call), success/expired/invalid
    states. `ForgotPasswordPage` / `MagicLinkRequestPage`: non-enumerating success
    copy shown regardless of mocked response.
- **E2E (Playwright), `frontend/e2e/` (one minimal test):** password-reset round
  trip — register/seed a user, request a reset, **capture the link from the
  `FileEmailSender` output dir** (or a test-only capture hook; no real SMTP),
  open `/reset-password?token=…`, set a new password, then sign in with it. Keep
  it to one scenario to stay within budget; magic-link/verify are covered by
  integration + Vitest.
- **Performance/budget note:** every email uses the capturing fake enqueuer (no
  worker, no socket); expiry uses the injected clock (no real waiting); the single
  Playwright case reads the link from the file sender, never a live inbox. No test
  starts Mailpit or calls Resend.

## 9. Definition of Done

- [ ] All requirements in §5 implemented: `auth_tokens` table + migration
      (`down_revision` = current head); `services/auth_tokens.py` token service
      (hash-at-rest, single-use, expiry, older-token invalidation, FOR UPDATE on
      consume); the three flow services; the six endpoints + the registration
      change; `magic_login` template; rate-limit scopes; settings + `.env.example`.
- [ ] 103's throwaway-token `forgot-password` and registration enqueues are
      replaced with real persisted tokens; 103's delivery code and its two
      templates are reused **unchanged**. The ADR states the 104↔103 ownership
      split and which template (`magic_login`) was added.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green (unit + integration + Vitest + one e2e).
- [ ] **Full suite runs in < 2 minutes.**
- [ ] **No real external email in automated tests** — no Mailpit, no real SMTP,
      no Resend; sender + enqueuer faked; the e2e reads the link from the file
      sender.
- [ ] Non-enumeration verified: request endpoints return identical `202` and
      enqueue conditionally; callbacks use uniform 400/410 messages.
- [ ] Password reset revokes all sessions (tested) and confirms the email.
- [ ] No raw token is ever logged or persisted (only the sha256 hash is stored).
- [ ] Lint/format/type-check clean (`ruff`, `mypy`; ESLint/Prettier strict).
- [ ] New env vars documented in `.env.example`; ADR under `docs/` added.
- [ ] **No Overleaf code copied** (PasswordReset/Authentication studied for
      structure only; magic-link has no Overleaf equivalent and is original).
